"""Diagnosis: health, class list, photo prediction and advisory lookup."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.config import (
    ALLOWED_IMAGE_TYPES,
    CONFIDENCE_THRESHOLD,
    LANG_PATTERN,
    MAX_UPLOAD_BYTES,
    SUPPORTED_LANGUAGES,
)
from app.services import advice
from app.services.assistant import assistant
from app.services.inference import ModelNotTrainedError, predictor

router = APIRouter(prefix="/api", tags=["diagnosis"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": predictor.is_loaded,
        "arch": predictor.arch or None,
        "num_classes": len(predictor.class_names),
        "metrics": predictor.metrics,
        "languages": list(SUPPORTED_LANGUAGES),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "ai": assistant.status(),
        "features": {
            "heatmap": True,
            # Offline "this is not a leaf I know" check; needs a checkpoint from
            # training/finetune_field.py, which stores the statistics it uses.
            "unknown_detection": predictor.ood is not None,
            "calibrated": predictor.temperature != 1.0,
        },
    }


@router.get("/classes")
def classes(lang: str = Query("mr", pattern=LANG_PATTERN)) -> dict:
    """Every crop and disease the app can name — used for labels on the phone."""
    items = []
    for key, entry in predictor.remedies.items():
        if key.startswith("_"):
            continue
        items.append({
            "class_name": key,
            "crop": entry["crop"][lang],
            "disease": entry["disease"][lang],
            "healthy": entry["healthy"],
            "severity": entry["severity"],
            # False for crops only the AI vision model can name so far.
            "cnn": key in predictor.class_names,
        })
    items.sort(key=lambda x: (x["crop"], x["disease"]))
    return {"count": len(items), "language": lang, "classes": items}


@router.post("/predict")
async def predict(
    file: UploadFile = File(...),
    lang: str = Query("mr", pattern=LANG_PATTERN),
) -> JSONResponse:
    if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, f"Unsupported image type: {file.content_type}")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, "Empty file.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image larger than 12 MB. Please retake at lower resolution.")

    try:
        result = predictor.predict(image_bytes, lang=lang)
    except ModelNotTrainedError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # corrupt or unreadable image
        raise HTTPException(400, f"Could not read the image: {exc}") from exc

    result["speech_text"] = predictor.speech_text(result, lang)
    return JSONResponse(result)


@router.get("/advisory/{class_name:path}")
def advisory(class_name: str, lang: str = Query("mr", pattern=LANG_PATTERN)) -> dict:
    """Full advisory for one class, without a photo.

    Used to reopen a saved scan in another language, and to show the remedy
    for a crop that only the AI vision model recognised.
    """
    entry = predictor.remedy(class_name)
    if entry is None:
        raise HTTPException(404, f"Unknown class: {class_name}")
    result = {
        "language": lang,
        "prediction": predictor.describe(class_name, lang),
        "alternatives": [],
        "low_confidence": False,
        "advice": advice.plan(entry, lang),
        "disclaimer": predictor.remedies["_meta"]["disclaimer"][lang],
    }
    result["speech_text"] = predictor.speech_text(result, lang)
    return result
