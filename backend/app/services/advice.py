"""Treatment cost per acre and organic alternatives for one diagnosis.

Prices live in data/prices.json so a KVK or a dealer can correct them without
touching code; the organic options in data/organic.json are keyed by the
pathogen type recorded in remedies.json.
"""

from __future__ import annotations

import json

from app.config import ORGANIC_PATH, PRICES_PATH

PRICES: dict = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
ORGANIC: dict = json.loads(ORGANIC_PATH.read_text(encoding="utf-8"))


def _costed(item: dict, litres: float) -> dict:
    """One product at its dose, scaled to a one-acre spray."""
    qty = item["dose"] * litres  # dose is per litre of spray water
    price = PRICES.get(item["product"])
    cost = round(qty * price["per_unit"]) if price and price["unit"] == item["unit"] else None
    return {**item, "qty_per_acre": round(qty, 1), "cost_per_acre": cost}


def plan(entry: dict | None, lang: str) -> dict | None:
    """Everything the cost card needs. Costs are per acre per spray; the phone
    multiplies by the farmer's own acreage."""
    if not entry or entry.get("healthy"):
        return None
    litres = entry.get("spray_l_per_acre", 200)
    organic = ORGANIC.get(entry.get("pathogen_type", ""))
    return {
        "spray_litres_per_acre": litres,
        "chemical": [_costed(t, litres) for t in entry.get("treatments", [])],
        "organic": {
            "text": organic["text"][lang],
            "items": [_costed(t, litres) for t in organic["items"]],
        } if organic else None,
        "currency": "INR",
        "price_note": PRICES["_meta"]["note"],
    }
