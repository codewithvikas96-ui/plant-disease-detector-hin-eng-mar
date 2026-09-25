"""Loads the trained checkpoint and turns an uploaded photo into a diagnosis."""

from __future__ import annotations

import io
import json
import time

import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from app.config import CONFIDENCE_THRESHOLD, MODEL_PATH, REMEDIES_PATH, SUPPORTED_LANGUAGES
from app.ml.model import FeatureTap, build_model, cam_layer, eval_transforms
from app.services import advice

# eval_transforms resizes the short side to img_size * 1.14, then centre-crops
# img_size. The heatmap only covers that crop, so the phone needs to know where it is.
RESIZE_FACTOR = 1.14


class ModelNotTrainedError(RuntimeError):
    """Raised when no checkpoint is present yet."""


class Predictor:
    def __init__(self) -> None:
        self.model = None
        self.class_names: list[str] = []
        self.arch: str = ""
        self.img_size: int = 224
        self.metrics: dict = {}
        self.transform = None
        self.temperature: float = 1.0
        self.ood: dict | None = None
        self._tap: FeatureTap | None = None
        self._cam_module = None
        self.remedies: dict = json.loads(REMEDIES_PATH.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- loading
    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        """Load the checkpoint into memory. Safe to call repeatedly."""
        if self.is_loaded:
            return
        if not MODEL_PATH.exists():
            raise ModelNotTrainedError(
                f"No trained model at {MODEL_PATH}. Run training/train_plantvillage.ipynb "
                "on Colab and copy plant_disease_model.pt into backend/models/."
            )

        # weights_only: the checkpoint holds only tensors, numbers and strings, so
        # refuse anything that would need arbitrary unpickling.
        ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
        self.class_names = ckpt["class_names"]
        self.arch = ckpt.get("arch", "mobilenet_v3_large")
        self.img_size = ckpt.get("img_size", 224)
        self.metrics = ckpt.get("metrics", {})
        # Written by training/finetune_field.py. Older checkpoints have neither,
        # and the app then behaves exactly as before.
        self.temperature = float(ckpt.get("temperature", 1.0))
        self.ood = ckpt.get("ood")

        model = build_model(len(self.class_names), arch=self.arch, pretrained=False)
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        # Inference-only server: weight gradients are pure overhead. Grad-CAM
        # still works because it differentiates activations, not weights.
        for p in model.parameters():
            p.requires_grad_(False)

        self.model = model
        self.transform = eval_transforms(self.img_size)
        self._tap = FeatureTap(model)
        self._cam_module = cam_layer(model, self.arch)

        unknown = [c for c in self.class_names if c not in self.remedies]
        if unknown:
            print(f"[warn] {len(unknown)} class(es) have no remedy entry: {unknown[:5]}")

    # ------------------------------------------------------------- predicting
    def predict(self, image_bytes: bytes, lang: str = "mr", top_k: int = 3) -> dict:
        self.load()
        if lang not in SUPPORTED_LANGUAGES:
            lang = "mr"

        image = Image.open(io.BytesIO(image_bytes))
        # Phone cameras store rotation in EXIF; without this a sideways photo
        # gets cropped wrongly and accuracy drops for no good reason.
        image = ImageOps.exif_transpose(image).convert("RGB")

        tensor = self.transform(image).unsqueeze(0)

        started = time.perf_counter()
        logits, heat = self._forward_with_cam(tensor)
        probs = F.softmax(logits / self.temperature, dim=0)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

        k = min(top_k, len(self.class_names))
        top_probs, top_idx = torch.topk(probs, k)

        predictions = [
            self.describe(self.class_names[i], lang, float(p))
            for p, i in zip(top_probs.tolist(), top_idx.tolist())
        ]
        best = predictions[0]
        unknown = self._out_of_distribution(logits)

        return {
            "language": lang,
            "inference_ms": elapsed_ms,
            "low_confidence": best["confidence"] < CONFIDENCE_THRESHOLD or unknown["is_unknown"],
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "prediction": best,
            "alternatives": predictions[1:],
            "unknown": unknown,
            "heatmap": {"grid": heat, "box": self._crop_box(image.size)},
            "advice": advice.plan(self.remedies.get(best["class_name"]), lang),
            "disclaimer": self.remedies["_meta"]["disclaimer"][lang],
        }

    def _forward_with_cam(self, tensor: torch.Tensor) -> tuple[torch.Tensor, list[list[float]]]:
        """One forward pass that yields both the logits and a Grad-CAM map.

        Grad-CAM (Selvaraju et al. 2017) weights each channel of the last conv
        block by how much it pushed the winning class up, showing *where* on
        the leaf the model looked. A judge can see it is looking at the lesion,
        not the background.
        """
        captured = {}

        def keep(_module, _inputs, output):
            output.retain_grad()
            captured["act"] = output

        handle = self._cam_module.register_forward_hook(keep)
        try:
            with torch.enable_grad():
                x = tensor.clone().requires_grad_(True)
                logits = self.model(x)[0]
                logits[logits.argmax()].backward()
        finally:
            handle.remove()

        act, grad = captured["act"], captured["act"].grad
        weights = grad.mean(dim=(2, 3), keepdim=True)
        cam = F.relu((weights * act).sum(dim=1))[0]
        cam = cam / cam.max().clamp(min=1e-8)
        grid = [[round(float(v), 2) for v in row] for row in cam.detach()]
        return logits.detach(), grid

    def _out_of_distribution(self, logits: torch.Tensor) -> dict:
        """Is this photo something the model was never trained on?

        Softmax always sums to 1 over the known diseases, so a photo of a hand
        can still come out "92% Early blight". Two checks catch that: the
        embedding's cosine similarity to the nearest class prototype, and the
        energy score. Thresholds were set on held-out leaves during training.
        """
        if not self.ood or self._tap.features is None:
            return {"is_unknown": False, "checked": False}
        feats = F.normalize(self._tap.features.detach(), dim=1)[0]
        similarity = float((self.ood["prototypes"] @ feats).max())
        energy = float(self.temperature * torch.logsumexp(logits / self.temperature, dim=0))
        return {
            "is_unknown": similarity < self.ood["cos_threshold"] or energy < self.ood["energy_threshold"],
            "checked": True,
            "similarity": round(similarity, 3),
            "energy": round(energy, 2),
        }

    def _crop_box(self, size: tuple[int, int]) -> list[float]:
        """The centre crop the model saw, as fractions of the uploaded photo."""
        w, h = size
        side = min(w, h) / RESIZE_FACTOR
        return [round((w - side) / 2 / w, 4), round((h - side) / 2 / h, 4),
                round(side / w, 4), round(side / h, 4)]

    # --------------------------------------------------------------- advisory
    def remedy(self, class_name: str | None) -> dict | None:
        """The remedies.json entry for a class, or None (also for "_meta")."""
        if not class_name or class_name.startswith("_"):
            return None
        return self.remedies.get(class_name)

    def describe(self, class_name: str, lang: str, confidence: float | None = None) -> dict:
        """Attach the localised advisory text to one class."""
        entry = self.remedies.get(class_name)
        conf = round(confidence, 4) if confidence is not None else None
        if entry is None or class_name.startswith("_"):
            # Should not happen — but never crash a farmer's request over it.
            return {
                "class_name": class_name,
                "confidence": conf,
                "healthy": False,
                "crop": class_name.split("___")[0].replace("_", " "),
                "disease": class_name.split("___")[-1].replace("_", " "),
                "symptoms": "",
                "remedy": "",
                "prevention": "",
                "pathogen": "",
                "severity": "unknown",
            }

        return {
            "class_name": class_name,
            "confidence": conf,
            "healthy": entry["healthy"],
            "severity": entry["severity"],
            "pathogen": entry["pathogen"],
            "crop": entry["crop"][lang],
            "disease": entry["disease"][lang],
            "symptoms": entry["symptoms"][lang],
            "remedy": entry["remedy"][lang],
            "prevention": entry["prevention"][lang],
        }

    def speech_text(self, result: dict, lang: str) -> str:
        """Flatten a result into one paragraph for text-to-speech."""
        p = result["prediction"]
        joiner = {
            "mr": ("रोग", "खात्री", "लक्षणे", "उपाय", "प्रतिबंध", "निरोगी पान आहे"),
            "hi": ("रोग", "निश्चितता", "लक्षण", "उपाय", "बचाव", "पत्ती स्वस्थ है"),
            "en": ("Disease", "Confidence", "Symptoms", "Remedy", "Prevention", "The leaf is healthy"),
        }[lang]

        if p["healthy"]:
            head = f"{p['crop']}. {joiner[5]}."
        else:
            head = f"{p['crop']}. {joiner[0]}: {p['disease']}."
        if p.get("confidence") is not None:
            head += f" {joiner[1]} {int(round(p['confidence'] * 100))} %."

        return " ".join([
            head,
            f"{joiner[2]}: {p['symptoms']}",
            f"{joiner[3]}: {p['remedy']}",
            f"{joiner[4]}: {p['prevention']}",
        ])


predictor = Predictor()
