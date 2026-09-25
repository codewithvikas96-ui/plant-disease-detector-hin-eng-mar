"""Groq-powered assistant: follow-up chat, vision second opinion, speech-to-text."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import AI_RATE_LIMIT_PER_MIN, LANG_PATTERN, MAX_AUDIO_BYTES, MAX_UPLOAD_BYTES
from app.ratelimit import RateLimiter, client_key
from app.services import weather
from app.services.assistant import AIRequestError, AIUnavailableError, assistant, build_advisory
from app.services.inference import predictor

router = APIRouter(prefix="/api/ai", tags=["assistant"])

AUDIO_EXTENSIONS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4",
                    "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-m4a": "m4a"}

limiter = RateLimiter(limit=AI_RATE_LIMIT_PER_MIN, window_s=60)


def _guard(request: Request) -> None:
    if not assistant.enabled:
        raise HTTPException(503, "AI assistant is off: set GROQ_API_KEY in .env.")
    if not limiter.allow(client_key(request)):
        raise HTTPException(429, "Too many AI requests. Please wait a minute.")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AIRequestError):
        return HTTPException(exc.status, str(exc))
    return HTTPException(503, str(exc))


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=1500)


class ChatRequest(BaseModel):
    lang: str = Field("mr", pattern=LANG_PATTERN)
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=16)
    # Only the class name is taken from the client. The advisory text itself
    # is looked up here, so a tampered request cannot feed the model fake doses.
    class_name: str | None = Field(None, max_length=120)
    confidence: float | None = Field(None, ge=0, le=1)
    low_confidence: bool = False
    alternatives: list[str] = Field(default_factory=list, max_length=5)
    # The vision model's independent answer, when it disagreed with the CNN.
    vision_match: str | None = Field(None, max_length=120)
    # Optional location, so answers about spraying can account for the forecast.
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    """Follow-up questions about a diagnosis. Streams plain UTF-8 text."""
    _guard(request)
    if req.messages[-1].role != "user":
        raise HTTPException(422, "The last message must come from the user.")

    advisory = None
    entry = predictor.remedy(req.class_name)
    if entry:
        alts = [
            f"{e['crop']['en']} - {e['disease']['en']}"
            for e in map(predictor.remedy, req.alternatives) if e
        ]
        advisory = build_advisory(entry, req.lang, req.confidence, req.low_confidence, alts)

        second = predictor.remedy(req.vision_match) if req.vision_match != req.class_name else None
        if second:
            advisory += (
                "\n\nSECOND OPINION — a separate vision AI looked at the same photo and "
                "thinks it may instead be the disease below. The two models disagree, so "
                "tell the farmer both possibilities and to confirm with an expert before "
                "spraying. Use this advisory's doses if discussing this disease:\n"
                + build_advisory(second, req.lang, None, False, [])
            )

    if req.lat is not None and req.lon is not None:
        try:
            forecast = weather.as_text(await weather.forecast(req.lat, req.lon))
            advisory = (advisory or "") + "\n\nLOCAL WEATHER (use it when advising when to spray):\n" + forecast
        except Exception:
            pass  # weather is a bonus; never fail the answer over it

    try:
        chunks = await assistant.chat_stream([m.model_dump() for m in req.messages], req.lang, advisory)
    except (AIUnavailableError, AIRequestError) as exc:
        raise _http_error(exc) from exc

    return StreamingResponse(
        chunks,
        media_type="text/plain; charset=utf-8",
        # Stops proxies (including the Cloudflare tunnel) from buffering the
        # stream, which would make the answer appear all at once at the end.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/second-opinion")
async def second_opinion(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Query("mr", pattern=LANG_PATTERN),
    cnn_class: str = Query(..., max_length=120),
) -> dict:
    """An independent vision-model read of the same photo, compared with the CNN."""
    _guard(request)
    image_bytes = await file.read()
    if not image_bytes or len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Missing or oversized image.")

    # Every class with an advisory, including crops the CNN has not been
    # trained on yet — for those the vision model is the only diagnosis.
    classes = [k for k in predictor.remedies if not k.startswith("_")]
    try:
        opinion = await assistant.second_opinion(image_bytes, classes)
    except (AIUnavailableError, AIRequestError) as exc:
        raise _http_error(exc) from exc
    except Exception as exc:  # PIL could not decode the image
        raise HTTPException(400, f"Could not read the image: {exc}") from exc

    best = opinion["best_match"]
    if not opinion["is_plant_leaf"]:
        verdict = "not_leaf"
    elif best == cnn_class:
        verdict = "agrees"
    elif best == "OTHER":
        verdict = "unknown"
    elif best not in predictor.class_names:
        verdict = "extended"  # a crop the CNN cannot name, e.g. cotton or onion
    else:
        verdict = "disagrees"

    entry = predictor.remedy(best)
    label = f"{entry['crop'][lang]} — {entry['disease'][lang]}" if entry else None
    return {**opinion, "verdict": verdict, "best_match_label": label, "model": assistant.vision_model}


@router.post("/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Query("mr", pattern=LANG_PATTERN),
) -> dict:
    """Speech to text for spoken questions."""
    _guard(request)
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "Empty recording.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording too long.")

    # Groq detects the format from the file extension, and browsers differ:
    # Chrome records webm, Safari mp4.
    base_type = (file.content_type or "audio/webm").split(";")[0].strip().lower()
    ext = AUDIO_EXTENSIONS.get(base_type, "webm")
    try:
        text = await assistant.transcribe(audio, f"question.{ext}", lang)
    except (AIUnavailableError, AIRequestError) as exc:
        raise _http_error(exc) from exc
    return {"text": text, "language": lang}
