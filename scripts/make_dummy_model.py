"""Create an UNTRAINED checkpoint so you can exercise the app before training.

This exists only to test the plumbing — upload, inference, the result card, the
Marathi/Hindi text and the voice button — without waiting for Colab. Its
predictions are random and it must never be used for a real demo.

    .venv/Scripts/python scripts/make_dummy_model.py

Delete backend/models/plant_disease_model.pt and replace it with the real
checkpoint from Colab before the actual presentation.
"""

import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.model import DEFAULT_ARCH, IMG_SIZE, build_model, save_checkpoint  # noqa: E402

remedies = json.loads((ROOT / "backend" / "data" / "remedies.json").read_text(encoding="utf-8"))
class_names = sorted(k for k in remedies if not k.startswith("_"))

out_path = ROOT / "backend" / "models" / "plant_disease_model.pt"
out_path.parent.mkdir(parents=True, exist_ok=True)

if out_path.exists():
    answer = input(f"{out_path.name} already exists. Overwrite with an UNTRAINED model? [y/N] ")
    if answer.strip().lower() != "y":
        raise SystemExit("Cancelled.")

torch.manual_seed(0)
model = build_model(len(class_names), arch=DEFAULT_ARCH, pretrained=False)
save_checkpoint(
    out_path,
    model,
    class_names,
    DEFAULT_ARCH,
    IMG_SIZE,
    {"val_accuracy": 0.0, "note": "UNTRAINED placeholder — random predictions"},
)

print(f"Wrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
print(f"{len(class_names)} classes. Predictions are RANDOM — replace before demoing.")
