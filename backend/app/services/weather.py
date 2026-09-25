"""Weather-aware spray advice from the free Open-Meteo forecast (no API key).

A correct remedy sprayed two hours before rain is money washed off the leaf,
and most fungal blights explode after long humid spells. This module turns a
48-hour forecast into three things a farmer can act on:

  * spray windows   the next dry, calm, not-too-hot daylight hours
  * rain warning    when the next rain is due
  * disease risk    how many hours ahead favour fungal spread
"""

from __future__ import annotations

import time
from datetime import datetime

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_S = 30 * 60

# Standard knapsack-spraying guidance: rain within ~4 hours washes the product
# off, wind above ~15 km/h drifts it, and above ~32 C droplets evaporate and
# leaves scorch.
RAIN_FREE_HOURS_AFTER = 4
MAX_RAIN_PROB = 30
MAX_WIND_KMH = 15
MAX_TEMP_C = 32
MIN_TEMP_C = 8
FIRST_HOUR, LAST_HOUR = 6, 18  # daylight; spraying in the dark misses the leaves

_cache: dict[tuple[float, float], tuple[float, dict]] = {}


async def forecast(lat: float, lon: float) -> dict:
    """Spray advice for a location, cached for 30 minutes per ~1 km cell."""
    key = (round(lat, 2), round(lon, 2))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]

    params = {
        "latitude": key[0], "longitude": key[1],
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,wind_speed_10m",
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
        "forecast_days": 3,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    result = summarise(data)
    _cache[key] = (time.monotonic(), result)
    if len(_cache) > 2000:
        _cache.clear()
    return result


def summarise(data: dict) -> dict:
    h = data["hourly"]
    times = [datetime.fromisoformat(t) for t in h["time"]]
    now = datetime.fromisoformat(data["current"]["time"]).replace(minute=0)
    start = next((i for i, t in enumerate(times) if t >= now), 0)
    end = min(start + 48, len(times))

    def val(name: str, i: int) -> float:
        v = h[name][i]
        return 0.0 if v is None else float(v)

    def dry_after(i: int) -> bool:
        for j in range(i, min(i + RAIN_FREE_HOURS_AFTER, len(times))):
            if val("precipitation_probability", j) >= MAX_RAIN_PROB or val("precipitation", j) >= 0.2:
                return False
        return True

    good = []
    for i in range(start, end):
        ok = (FIRST_HOUR <= times[i].hour <= LAST_HOUR
              and val("wind_speed_10m", i) < MAX_WIND_KMH
              and MIN_TEMP_C <= val("temperature_2m", i) <= MAX_TEMP_C
              and dry_after(i))
        good.append((i, ok))

    windows, run = [], []
    for i, ok in good:
        if ok:
            run.append(i)
        elif run:
            windows.append(run)
            run = []
    if run:
        windows.append(run)
    windows = [
        {"start": times[w[0]].isoformat(), "end": times[w[-1]].isoformat(), "hours": len(w)}
        for w in windows if len(w) >= 2  # one isolated hour is not a usable window
    ][:3]

    rain_24 = range(start, min(start + 24, len(times)))
    first_rain = next((times[i].isoformat() for i in range(start, end)
                       if val("precipitation_probability", i) >= 50 or val("precipitation", i) >= 0.5), None)

    # Long leaf wetness at mild temperatures is what late blight, early blight
    # and most leaf spots need to spread.
    humid_hours = sum(1 for i in range(start, end)
                      if val("relative_humidity_2m", i) >= 90 and 15 <= val("temperature_2m", i) <= 28)
    risk = "high" if humid_hours >= 10 else "medium" if humid_hours >= 4 else "low"

    cur = data["current"]
    return {
        "current": {
            "temperature": cur.get("temperature_2m"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "precipitation": cur.get("precipitation"),
        },
        "windows": windows,
        "rain": {
            "next_24h_mm": round(sum(val("precipitation", i) for i in rain_24), 1),
            "max_probability": max((val("precipitation_probability", i) for i in rain_24), default=0),
            "first_rain": first_rain,
        },
        # One entry per hour for the phone's 48-hour ribbon.
        "hourly": [
            {"t": times[i].isoformat(), "good": ok,
             "rain": val("precipitation_probability", i) >= 50 or val("precipitation", i) >= 0.5}
            for i, ok in good
        ],
        "disease_risk": risk,
        "humid_hours": humid_hours,
        "timezone": data.get("timezone"),
    }


def as_text(w: dict) -> str:
    """Compact English summary for the chat model's context."""
    parts = [
        f"Now {w['current']['temperature']} C, humidity {w['current']['humidity']}%, wind {w['current']['wind']} km/h.",
        f"Rain next 24 h: {w['rain']['next_24h_mm']} mm (max chance {w['rain']['max_probability']}%)."
        + (f" First rain expected {w['rain']['first_rain']}." if w["rain"]["first_rain"] else ""),
        f"Fungal disease risk from humidity over the next 48 h: {w['disease_risk']} ({w['humid_hours']} humid hours).",
    ]
    if w["windows"]:
        parts.append("Good spray windows (local time): "
                     + "; ".join(f"{x['start']} to {x['end']}" for x in w["windows"]) + ".")
    else:
        parts.append("No good spray window in the next 48 hours.")
    return " ".join(parts)
