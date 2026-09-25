"""remedies.json is what farmers act on, so its shape is checked like code."""

import json

from app.config import ORGANIC_PATH, PRICES_PATH

LANGS = ("en", "hi", "mr")
TEXT_FIELDS = ("crop", "disease", "symptoms", "remedy", "prevention")


def classes(remedies):
    return {k: v for k, v in remedies.items() if not k.startswith("_")}


def test_every_text_field_is_in_all_three_languages(remedies):
    for name, entry in classes(remedies).items():
        for field in TEXT_FIELDS:
            for lang in LANGS:
                assert entry[field][lang].strip(), f"{name}.{field}.{lang} is empty"


def test_every_product_has_a_price(remedies):
    prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    organic = json.loads(ORGANIC_PATH.read_text(encoding="utf-8"))
    products = {t["product"] for e in classes(remedies).values() for t in e["treatments"]}
    products |= {i["product"] for k, v in organic.items() if not k.startswith("_") for i in v["items"]}
    missing = products - prices.keys()
    assert not missing, f"no price for {missing}"


def test_treatment_doses_appear_in_the_remedy_text(remedies):
    """The cost card and the spoken remedy must never disagree on a dose."""
    for name, entry in classes(remedies).items():
        text = entry["remedy"]["en"]
        for t in entry["treatments"]:
            assert t["product"].split()[0] in text, f"{name}: {t['product']} not in remedy text"
            if t["unit"] != "l":
                assert f"{t['dose']:g} {t['unit']}" in text, f"{name}: dose {t['dose']} {t['unit']} not in text"


def test_no_antibiotic_is_recommended(remedies):
    """Streptomycin/tetracycline are no longer permitted on crops in India."""
    for name, entry in classes(remedies).items():
        text = entry["remedy"]["en"]
        if "Streptocycline" in text:
            assert "Do not use Streptocycline" in text, name
        assert all("strepto" not in t["product"].lower() for t in entry["treatments"]), name


def test_healthy_entries_have_no_treatment(remedies):
    for name, entry in classes(remedies).items():
        if entry["healthy"]:
            assert entry["treatments"] == [] and entry["severity"] == "none", name


def test_pathogen_types_have_organic_options(remedies):
    organic = json.loads(ORGANIC_PATH.read_text(encoding="utf-8"))
    for name, entry in classes(remedies).items():
        if not entry["healthy"]:
            assert entry["pathogen_type"] in organic, f"{name}: {entry['pathogen_type']}"
