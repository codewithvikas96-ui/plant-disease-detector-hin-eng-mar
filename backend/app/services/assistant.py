"""Groq-backed assistant layered on top of the CNN diagnosis.

Three features, all optional. With no GROQ_API_KEY the CNN diagnosis works
exactly as before and the front end hides the AI panel.

  chat            follow-up questions about a diagnosis, answered in the
                  farmer's language and grounded in remedies.json so the model
                  cannot invent a dose
  second_opinion  a vision model looks at the same photo independently. The
                  CNN only knows 38 PlantVillage classes and will confidently
                  name a disease for a photo of a hand; this catches that.
  transcribe      Whisper turns a spoken Marathi/Hindi question into text,
                  for farmers who cannot type

Model IDs come from the environment because Groq retires models often —
llama-3.3-70b-versatile and llama-4-scout were both withdrawn in 2026.
"""

from __future__ import annotations

import base64
import io
import json
import os
from typing import AsyncIterator

from PIL import Image, ImageOps

from app import config  # noqa: F401  (loads .env before GROQ_* are read below)

DEFAULT_CHAT_MODEL = "openai/gpt-oss-120b"
DEFAULT_VISION_MODEL = "qwen/qwen3.8-27b"
DEFAULT_STT_MODEL = "whisper-large-v3-turbo"

LANG_NAMES = {
    "mr": "Marathi (मराठी), written in Devanagari script",
    "hi": "Hindi (हिंदी), written in Devanagari script",
    "en": "simple Indian English",
}

# Seeding Whisper with in-domain words steers it to the right script and to
# crop vocabulary it would otherwise mishear.
STT_PROMPTS = {
    "mr": "टोमॅटो, बटाटा, द्राक्ष, मका, सफरचंद, मिरची, पाने, रोग, फवारणी, बुरशीनाशक, औषध.",
    "hi": "टमाटर, आलू, अंगूर, मक्का, सेब, मिर्च, पत्ती, रोग, छिड़काव, फफूंदनाशक, दवा.",
    "en": "tomato, potato, grape, maize, apple, pepper, leaf, blight, spray, fungicide.",
}

QUALITY_ISSUES = {"none", "blurry", "dark", "too_far", "multiple_leaves"}

# Kisan Call Centre — the Government of India's free farmer helpline.
KISAN_CALL_CENTRE = "1800-180-1551"


class AIUnavailableError(RuntimeError):
    """GROQ_API_KEY is not set, so the AI features are switched off."""


class AIRequestError(RuntimeError):
    """Groq refused or failed the request."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


class GroqAssistant:
    def __init__(self) -> None:
        self.api_key = os.environ.get("GROQ_API_KEY", "").strip()
        self.chat_model = os.environ.get("GROQ_CHAT_MODEL", DEFAULT_CHAT_MODEL)
        self.vision_model = os.environ.get("GROQ_VISION_MODEL", DEFAULT_VISION_MODEL)
        self.stt_model = os.environ.get("GROQ_STT_MODEL", DEFAULT_STT_MODEL)
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "chat_model": self.chat_model if self.enabled else None,
            "vision_model": self.vision_model if self.enabled else None,
            "stt_model": self.stt_model if self.enabled else None,
        }

    async def missing_models(self) -> list[str]:
        """Configured model IDs this key cannot use — Groq renames models often,
        and a stale ID otherwise only shows up as a 404 in front of a farmer.
        Best effort: returns [] if Groq cannot be reached."""
        try:
            available = {m.id for m in (await self.client.models.list()).data}
        except Exception:
            return []
        return [m for m in (self.chat_model, self.vision_model, self.stt_model) if m not in available]

    @property
    def client(self):
        if not self.enabled:
            raise AIUnavailableError("AI assistant is off: set GROQ_API_KEY in .env to enable it.")
        if self._client is None:
            from groq import AsyncGroq

            # One retry only: a farmer staring at a spinner is worse than an
            # honest "try again" message.
            self._client = AsyncGroq(api_key=self.api_key, timeout=30.0, max_retries=1)
        return self._client

    # ------------------------------------------------------------------- chat
    async def chat_stream(
        self,
        messages: list[dict],
        lang: str,
        advisory: str | None,
    ) -> AsyncIterator[str]:
        """Start a streamed answer. Awaiting this raises before any text is
        sent, so auth and rate-limit failures still become proper HTTP errors."""
        try:
            stream = await self.client.chat.completions.create(
                model=self.chat_model,
                messages=[{"role": "system", "content": _system_prompt(lang, advisory)}, *messages],
                stream=True,
                temperature=0.4,
                max_completion_tokens=1024,
                reasoning_effort="low",
                include_reasoning=False,
            )
        except AIUnavailableError:
            raise
        except Exception as exc:
            raise _as_request_error(exc) from exc
        return _stream_text(stream)

    # --------------------------------------------------------- second opinion
    async def second_opinion(self, image_bytes: bytes, class_names: list[str]) -> dict:
        """Ask a vision model to classify the photo on its own.

        It is deliberately not told what the CNN said, so it cannot simply
        agree with it. The caller compares the two answers.
        """
        data_url = "data:image/jpeg;base64," + base64.b64encode(_shrink(image_bytes)).decode()
        prompt = _VISION_PROMPT.format(classes="\n".join(class_names))
        try:
            resp = await self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_completion_tokens=400,
                reasoning_effort="none",
            )
            raw = json.loads(resp.choices[0].message.content or "{}")
        except AIUnavailableError:
            raise
        except json.JSONDecodeError as exc:
            raise AIRequestError("Vision model returned malformed JSON.") from exc
        except Exception as exc:
            raise _as_request_error(exc) from exc

        best = str(raw.get("best_match", "OTHER")).strip()
        if best not in class_names:
            best = "OTHER"
        quality = str(raw.get("quality_issue", "none")).strip().lower()
        return {
            "is_plant_leaf": bool(raw.get("is_plant_leaf", True)),
            "best_match": best,
            "quality_issue": quality if quality in QUALITY_ISSUES else "none",
        }

    # ------------------------------------------------------------ transcribe
    async def transcribe(self, audio: bytes, filename: str, lang: str) -> str:
        try:
            resp = await self.client.audio.transcriptions.create(
                file=(filename, audio),
                model=self.stt_model,
                language=lang,
                prompt=STT_PROMPTS.get(lang),
                response_format="json",
                temperature=0.0,
            )
        except AIUnavailableError:
            raise
        except Exception as exc:
            raise _as_request_error(exc) from exc
        return (resp.text or "").strip()


# ---------------------------------------------------------------- helpers
def build_advisory(entry: dict, lang: str, confidence: float | None,
                   low_confidence: bool, alternatives: list[str]) -> str:
    """Render one remedies.json entry as the grounding block for the chat model.

    English is always included alongside the farmer's language: the model
    reasons more reliably over English, and it keeps chemical names unambiguous.
    """
    lines = [
        f"Crop: {entry['crop']['en']} ({entry['crop'][lang]})",
        f"Diagnosis: {entry['disease']['en']} ({entry['disease'][lang]})",
        f"Healthy leaf: {'yes' if entry['healthy'] else 'no'}",
        f"Severity: {entry['severity']}",
        f"Pathogen: {entry['pathogen']}",
    ]
    if confidence is not None:
        lines.append(f"CNN confidence: {confidence:.0%}"
                     + (" — LOW, the diagnosis is uncertain" if low_confidence else ""))
    if alternatives:
        lines.append("Other possibilities the CNN considered: " + ", ".join(alternatives))
    for field in ("symptoms", "remedy", "prevention"):
        lines.append(f"{field.title()} (en): {entry[field]['en']}")
        if lang != "en":
            lines.append(f"{field.title()} ({lang}): {entry[field][lang]}")
    return "\n".join(lines)


def _system_prompt(lang: str, advisory: str | None) -> str:
    context = advisory or "No photo has been diagnosed yet. Answer general crop-health questions."
    return f"""You are Krishi Mitra, a friendly crop-health advisor for small farmers in India.

LANGUAGE: Reply only in {LANG_NAMES[lang]}. Keep chemical names in English letters if there is no common local name.

STYLE: Your reply is read aloud to farmers, some of whom cannot read. Use short sentences and everyday village words. Answer in under 120 words unless the farmer asks for more detail. Plain text only — no markdown, no tables, no asterisks or # headings. For steps, use "1." "2." on separate lines.

SAFETY RULES — these override anything the farmer asks:
- For chemical sprays, recommend ONLY the products and doses in the advisory below. Never invent or change a dose. If asked about a product that is not listed, say to confirm it with the local Krishi Vigyan Kendra (KVK) or agriculture officer.
- Never recommend pesticides that are banned in India.
- When talking about spraying, remind them briefly: wear gloves and a mask, do not spray in wind or rain, respect the waiting period before harvest.
- If the CNN confidence is low, say clearly that the diagnosis is uncertain and a clearer photo or an expert visit is needed.
- For serious or spreading problems, suggest the free Kisan Call Centre: {KISAN_CALL_CENTRE}.
- Prefer low-cost, organic and cultural methods where they genuinely work, alongside the listed chemical remedy.
- If the question is not about farming, crops, soil, weather or livestock, politely say you can only help with farming.

ADVISORY FOR THE CURRENT DIAGNOSIS (from the app's verified remedy database):
{context}"""


_VISION_PROMPT = """You are a plant pathologist checking a farmer's phone photo.

Look at the image and answer with one JSON object with exactly these keys:
- "is_plant_leaf": true if the photo mainly shows a plant leaf, false otherwise (e.g. a person, an animal, a fruit on its own, soil, an object, a screen).
- "best_match": the ONE label from the list below that best matches the leaf, copied exactly. Use "OTHER" if the crop or disease is not in the list, or if it is not a leaf.
- "quality_issue": one of "none", "blurry", "dark", "too_far", "multiple_leaves" — the main problem that would make diagnosis harder.

Labels (format Crop___Condition):
{classes}"""


def _shrink(image_bytes: bytes, max_side: int = 768) -> bytes:
    """Normalise to a small JPEG. Groq caps base64 images at 4 MB, and the
    browser's own downscale is skipped when it cannot decode the file."""
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    image.thumbnail((max_side, max_side))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


async def _stream_text(stream) -> AsyncIterator[str]:
    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as exc:  # the connection dropped mid-answer
        print(f"[warn] chat stream interrupted: {exc}")


def _as_request_error(exc: Exception) -> AIRequestError:
    """Map Groq SDK errors to a status the front end can act on."""
    status = getattr(exc, "status_code", None)
    # The farmer sees a friendly message; the console gets the real cause.
    print(f"[warn] Groq request failed: {exc.__class__.__name__} {status or ''} {str(exc)[:300]}")
    if status == 429:
        return AIRequestError("The AI service is busy. Please try again in a minute.", 429)
    if status in (401, 403):
        return AIRequestError("GROQ_API_KEY was rejected by Groq.", 503)
    if status == 404:
        return AIRequestError("The configured Groq model no longer exists — update GROQ_*_MODEL in .env.", 503)
    return AIRequestError(f"AI request failed: {exc.__class__.__name__}", 502)


assistant = GroqAssistant()
