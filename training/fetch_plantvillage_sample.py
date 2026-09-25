"""Download a small, balanced PlantVillage sample from the public GitHub mirror.

Fine-tuning on field photos alone would make the model forget the clean
PlantVillage look it was trained on, so every fine-tuning batch mixes in these
images as an anchor. 60 per class is ~2,300 images, ~35 MB. No account needed.

    python training/fetch_plantvillage_sample.py [--per-class 60]
"""

from __future__ import annotations

import argparse
import json
import random
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "spMohanty/PlantVillage-Dataset"
API = f"https://api.github.com/repos/{REPO}/contents/raw/color"
RAW = f"https://raw.githubusercontent.com/{REPO}/master/raw/color"
OUT = Path(__file__).resolve().parent / "data" / "plantvillage_sample"
HEADERS = {"User-Agent": "plant-disease-detector-training"}


def get_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as exc:
        print(f"  [skip] {dest.name}: {exc}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    classes = sorted(e["name"] for e in get_json(API) if e["type"] == "dir")
    print(f"{len(classes)} classes")

    jobs = []
    for cls in classes:
        # The contents API returns up to 1,000 entries — plenty to sample from.
        files = [e["name"] for e in get_json(f"{API}/{urllib.parse.quote(cls)}") if e["type"] == "file"]
        picked = rng.sample(files, min(args.per_class, len(files)))
        (OUT / cls).mkdir(parents=True, exist_ok=True)
        for name in picked:
            url = f"{RAW}/{urllib.parse.quote(cls)}/{urllib.parse.quote(name)}"
            jobs.append((url, OUT / cls / name))

    with ThreadPoolExecutor(max_workers=16) as pool:
        ok = sum(pool.map(lambda j: download(*j), jobs))
    print(f"downloaded {ok}/{len(jobs)} images into {OUT}")


if __name__ == "__main__":
    main()
