"""Server-side text-to-speech for Marathi and Hindi."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import LANG_PATTERN, TTS_CACHE_DIR

router = APIRouter(prefix="/api", tags=["speech"])


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    lang: str = Field("mr", pattern=LANG_PATTERN)


@router.post("/tts")
def tts(req: SpeakRequest) -> FileResponse:
    """Server-side speech, used when the phone has no Marathi or Hindi voice.

    Most Android phones ship a hi-IN voice but very few ship mr-IN, so the
    browser alone cannot be relied on for the Marathi demo. Needs internet.
    """
    try:
        from gtts import gTTS
    except ImportError as exc:
        raise HTTPException(503, "gTTS is not installed on the server.") from exc

    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{req.lang}:{req.text}".encode("utf-8")).hexdigest()[:24]
    mp3_path = TTS_CACHE_DIR / f"{digest}.mp3"

    if not mp3_path.exists():
        try:
            # tld='co.in' gives noticeably better Indian pronunciation for en.
            gTTS(text=req.text, lang=req.lang, tld="co.in", slow=False).save(str(mp3_path))
        except Exception as exc:
            mp3_path.unlink(missing_ok=True)
            raise HTTPException(503, f"Speech generation failed (needs internet): {exc}") from exc

    return FileResponse(mp3_path, media_type="audio/mpeg", filename=f"advisory_{req.lang}.mp3")
