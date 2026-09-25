"""In the field: spray-timing weather and the anonymous outbreak map."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import LANG_PATTERN, REPORT_RATE_LIMIT_PER_MIN
from app.ratelimit import RateLimiter, client_key
from app.services import outbreaks, weather
from app.services.inference import predictor

router = APIRouter(prefix="/api", tags=["field"])

report_limiter = RateLimiter(limit=REPORT_RATE_LIMIT_PER_MIN, window_s=60)


@router.get("/weather")
async def spray_weather(lat: float = Query(..., ge=-90, le=90),
                        lon: float = Query(..., ge=-180, le=180)) -> dict:
    """48-hour spray windows, rain warning and humidity-driven disease risk."""
    try:
        return await weather.forecast(lat, lon)
    except Exception as exc:
        raise HTTPException(503, f"Weather service unavailable: {exc.__class__.__name__}") from exc


class ReportRequest(BaseModel):
    class_name: str = Field(..., max_length=120)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    source: Literal["cnn", "vision"] = "cnn"


@router.post("/report")
def report(req: ReportRequest, request: Request) -> dict:
    """Add one anonymous diagnosis to the outbreak map (opt-in on the phone)."""
    if not report_limiter.allow(client_key(request)):
        raise HTTPException(429, "Too many reports.")
    entry = predictor.remedy(req.class_name)
    if entry is None:
        raise HTTPException(422, "Unknown class.")
    if entry["healthy"]:
        return {"stored": False}  # the map shows disease, not healthy leaves
    outbreaks.record(req.class_name, req.lat, req.lon, req.source)
    return {"stored": True, "cell_km": 5}


@router.get("/outbreaks")
def outbreak_map(days: int = Query(30, ge=1, le=365),
                 lang: str = Query("mr", pattern=LANG_PATTERN)) -> dict:
    """Diseases reported per ~5 km cell, localised for the map popups."""
    cells = []
    for row in outbreaks.summary(days):
        entry = predictor.remedy(row["class_name"])
        if entry is None:
            continue
        cells.append({**row, "crop": entry["crop"][lang], "disease": entry["disease"][lang],
                      "severity": entry["severity"]})
    return {"days": days, "cell_km": 5, "cells": cells}
