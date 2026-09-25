"""Fine-tune the PlantVillage model on real field photos (PlantDoc).

PlantVillage leaves are shot on a plain background in studio light, so the
model scores 99.5% there and much worse on a farmer's photo. This script:

  1. measures that gap on the PlantDoc test set (the "before" number),
  2. fine-tunes on PlantDoc field photos mixed 1:1 with a PlantVillage sample,
     so the model learns field conditions without forgetting what it knew,
  3. fits a temperature so the confidence % means what it says,
  4. stores out-of-distribution statistics (class prototypes + thresholds) so
     the server can say "this is not a leaf I know" without the internet,
  5. optionally adds brand-new classes from --extra-dir (e.g. cotton, onion),
  6. writes a new checkpoint and prints before/after numbers for the report.

Runs on a laptop CPU in ~30 minutes, or on Colab in a few.

    python training/fetch_plantvillage_sample.py
    git clone --depth 1 https://github.com/pratikkayal/PlantDoc-Dataset training/data/plantdoc
    python training/finetune_field.py --epochs 6

Add new crops by putting images in class folders named like remedies.json keys:
    training/data/extra/Cotton___Bacterial_blight/*.jpg
    python training/finetune_field.py --extra-dir training/data/extra
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageFile, ImageOps
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.ml.model import MEAN, STD, FeatureTap, build_model, eval_transforms, final_linear, save_checkpoint  # noqa: E402

ImageFile.LOAD_TRUNCATED_IMAGES = True  # a few PlantDoc files are truncated web downloads

DATA = ROOT / "training" / "data"

# PlantDoc folder -> PlantVillage class. Every PlantDoc class has a PlantVillage twin.
PLANTDOC_MAP = {
    "Apple Scab Leaf": "Apple___Apple_scab",
    "Apple leaf": "Apple___healthy",
    "Apple rust leaf": "Apple___Cedar_apple_rust",
    "Bell_pepper leaf spot": "Pepper,_bell___Bacterial_spot",
    "Bell_pepper leaf": "Pepper,_bell___healthy",
    "Blueberry leaf": "Blueberry___healthy",
    "Cherry leaf": "Cherry_(including_sour)___healthy",
    "Corn Gray leaf spot": "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
    "Corn leaf blight": "Corn_(maize)___Northern_Leaf_Blight",
    "Corn rust leaf": "Corn_(maize)___Common_rust_",
    "Peach leaf": "Peach___healthy",
    "Potato leaf early blight": "Potato___Early_blight",
    "Potato leaf late blight": "Potato___Late_blight",
    "Raspberry leaf": "Raspberry___healthy",
    "Soyabean leaf": "Soybean___healthy",
    "Squash Powdery mildew leaf": "Squash___Powdery_mildew",
    "Strawberry leaf": "Strawberry___healthy",
    "Tomato Early blight leaf": "Tomato___Early_blight",
    "Tomato Septoria leaf spot": "Tomato___Septoria_leaf_spot",
    "Tomato leaf bacterial spot": "Tomato___Bacterial_spot",
    "Tomato leaf late blight": "Tomato___Late_blight",
    "Tomato leaf mosaic virus": "Tomato___Tomato_mosaic_virus",
    "Tomato leaf yellow virus": "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato leaf": "Tomato___healthy",
    "Tomato mold leaf": "Tomato___Leaf_Mold",
    "Tomato two spotted spider mites leaf": "Tomato___Spider_mites Two-spotted_spider_mite",
    "grape leaf black rot": "Grape___Black_rot",
    "grape leaf": "Grape___healthy",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


# ------------------------------------------------------------------ data
def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def load_cached(path: Path, short_side: int = 288) -> bytes | None:
    """Decode once, shrink, and keep as a small JPEG in memory.

    Some PlantDoc photos are 4000 px wide; decoding those every epoch would
    dominate CPU training time.
    """
    try:
        # Some PlantDoc names are ~250 characters; with the folder that passes
        # Windows' 260-character limit unless the path uses the \\?\ prefix.
        target = "\\\\?\\" + str(path.resolve()) if sys.platform == "win32" else path
        img = ImageOps.exif_transpose(Image.open(target)).convert("RGB")
        scale = short_side / min(img.size)
        if scale < 1:
            img = img.resize((round(img.width * scale), round(img.height * scale)), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception as exc:
        print(f"  [skip] {path.name}: {exc}")
        return None


class CachedDataset(Dataset):
    def __init__(self, items: list[tuple[bytes, int]], transform) -> None:
        self.items = items
        self.transform = transform

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i):
        data, label = self.items[i]
        return self.transform(Image.open(io.BytesIO(data)).convert("RGB")), label


def cache_all(samples: list[tuple[Path, int]]) -> list[tuple[bytes, int]]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        blobs = list(pool.map(lambda s: load_cached(s[0]), samples))
    return [(b, label) for b, (_, label) in zip(blobs, samples) if b is not None]


def split(samples: list, frac: float, seed: int) -> tuple[list, list]:
    """Per-class split so every class appears on both sides when it can."""
    by_class = defaultdict(list)
    for s in samples:
        by_class[s[1]].append(s)
    rng = random.Random(seed)
    a, b = [], []
    for items in by_class.values():
        rng.shuffle(items)
        k = max(1, round(len(items) * frac)) if len(items) > 1 else 0
        b += items[:k]
        a += items[k:]
    return a, b


# -------------------------------------------------------------- transforms
def field_train_transforms(img_size: int = 224) -> transforms.Compose:
    """Harsher than the original augmentation: field photos are off-centre,
    partly occluded, blurred and shot in harsh or dim light."""
    return transforms.Compose([
        transforms.RandomResizedCrop(img_size, scale=(0.35, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(30),
        transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.05),
        transforms.RandomApply([transforms.GaussianBlur(5, sigma=(0.1, 2.0))], p=0.3),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
        transforms.RandomErasing(p=0.25, scale=(0.02, 0.15)),
    ])


# ------------------------------------------------------------- evaluation
@torch.inference_mode()
def collect(model: nn.Module, loader: DataLoader) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Logits, penultimate features and labels for a whole loader."""
    model.eval()
    tap = FeatureTap(model)
    logits, feats, labels = [], [], []
    for x, y in loader:
        logits.append(model(x))
        feats.append(tap.features.clone())
        labels.append(y)
    tap.close()
    return torch.cat(logits), torch.cat(feats), torch.cat(labels)


def accuracy(logits: torch.Tensor, labels: torch.Tensor, k: int = 1) -> float:
    topk = logits.topk(k, dim=1).indices
    return (topk == labels[:, None]).any(dim=1).float().mean().item()


def fit_temperature(logits: torch.Tensor, labels: torch.Tensor) -> float:
    """Temperature scaling (Guo et al. 2017): one scalar that makes the softmax
    probability match how often the model is actually right."""
    # Logits collected under inference_mode cannot take part in autograd; a
    # clone made outside it is an ordinary tensor.
    logits, labels = logits.clone(), labels.clone()
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits / log_t.exp(), labels)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp().clamp(0.5, 5.0))


def ece(logits: torch.Tensor, labels: torch.Tensor, bins: int = 10) -> float:
    """Expected calibration error: average gap between confidence and accuracy."""
    probs = logits.softmax(1)
    conf, pred = probs.max(1)
    correct = (pred == labels).float()
    edges = torch.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            total += mask.float().mean() * (conf[mask].mean() - correct[mask].mean()).abs()
    return float(total)


def energy(logits: torch.Tensor, t: float) -> torch.Tensor:
    """Negative free energy (Liu et al. 2020). Higher means more in-distribution."""
    return t * torch.logsumexp(logits / t, dim=1)


def max_cosine(feats: torch.Tensor, prototypes: torch.Tensor) -> torch.Tensor:
    return (F.normalize(feats, dim=1) @ prototypes.T).max(dim=1).values


# --------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(ROOT / "backend" / "models" / "plant_disease_model.pt"))
    ap.add_argument("--out", default=str(ROOT / "backend" / "models" / "plant_disease_model_field.pt"))
    ap.add_argument("--plantdoc", default=str(DATA / "plantdoc"))
    ap.add_argument("--plantvillage", default=str(DATA / "plantvillage_sample"))
    ap.add_argument("--extra-dir", default=None, help="ImageFolder of additional classes")
    ap.add_argument("--ood-dir", default=str(DATA / "ood"), help="non-leaf photos, evaluation only")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--weights", default=None,
                    help="skip training and calibrate these fine-tuned weights (a *.raw.pt from a previous run)")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if args.threads:
        torch.set_num_threads(args.threads)

    ckpt = torch.load(args.base, map_location="cpu", weights_only=False)
    arch, img_size = ckpt.get("arch", "mobilenet_v3_large"), ckpt.get("img_size", 224)
    base_classes: list[str] = list(ckpt["class_names"])
    class_names = list(base_classes)

    # ---- gather samples -------------------------------------------------
    def plantdoc(split_name: str) -> list[tuple[Path, int]]:
        out = []
        for folder in sorted((Path(args.plantdoc) / split_name).iterdir()):
            target = PLANTDOC_MAP.get(folder.name)
            if target is None:
                print(f"  [warn] unmapped PlantDoc folder: {folder.name}")
                continue
            out += [(p, class_names.index(target)) for p in list_images(folder)]
        return out

    pv = [(p, class_names.index(folder.name))
          for folder in sorted(Path(args.plantvillage).iterdir()) if folder.name in class_names
          for p in list_images(folder)]

    extra = []
    if args.extra_dir:
        for folder in sorted(Path(args.extra_dir).iterdir()):
            if not folder.is_dir():
                continue
            if folder.name not in class_names:
                class_names.append(folder.name)
            extra += [(p, class_names.index(folder.name)) for p in list_images(folder)]
        print(f"extra classes: {class_names[len(base_classes):]}  ({len(extra)} images)")

    pd_train_all, pd_test = plantdoc("train"), plantdoc("test")
    pd_train, pd_val = split(pd_train_all, 0.15, args.seed)
    pv_train, pv_val = split(pv, 0.2, args.seed)
    ex_train, ex_val = split(extra, 0.2, args.seed) if extra else ([], [])

    print("caching images...")
    t0 = time.time()
    sets = {name: cache_all(s) for name, s in {
        "pd_train": pd_train, "pd_val": pd_val, "pd_test": pd_test,
        "pv_train": pv_train, "pv_val": pv_val, "ex_train": ex_train, "ex_val": ex_val,
    }.items()}
    print({k: len(v) for k, v in sets.items()}, f"{time.time() - t0:.0f}s")

    eval_tf = eval_transforms(img_size)
    loader = lambda items: DataLoader(CachedDataset(items, eval_tf), batch_size=64)
    val_items = sets["pd_val"] + sets["pv_val"] + sets["ex_val"]

    # ---- model ------------------------------------------------------------
    model = build_model(len(base_classes), arch=arch, pretrained=False)
    model.load_state_dict(ckpt["state_dict"])

    def report(tag: str) -> dict:
        out = {}
        for name in ("pd_test", "pv_val"):
            logits, _, labels = collect(model, loader(sets[name]))
            out[name] = {"top1": accuracy(logits, labels), "top3": accuracy(logits, labels, 3)}
        print(f"[{tag}] field (PlantDoc test) top1 {out['pd_test']['top1']:.1%} top3 {out['pd_test']['top3']:.1%}"
              f" | lab (PlantVillage holdout) top1 {out['pv_val']['top1']:.1%}")
        return out

    before = report("before")

    if len(class_names) > len(base_classes):
        # Grow the head: keep every learned row, add fresh rows for new classes.
        old = final_linear(model)
        new = nn.Linear(old.in_features, len(class_names))
        with torch.no_grad():
            new.weight[: len(base_classes)] = old.weight
            new.bias[: len(base_classes)] = old.bias
        if arch == "resnet18":
            model.fc = new
        elif arch == "efficientnet_b0":
            model.classifier[1] = new
        else:
            model.classifier[3] = new

    # ---- training -----------------------------------------------------------
    train_items = sets["pd_train"] + sets["pv_train"] + sets["ex_train"]
    domain_sizes = Counter()
    domains = ["pd"] * len(sets["pd_train"]) + ["pv"] * len(sets["pv_train"]) + ["ex"] * len(sets["ex_train"])
    domain_sizes.update(domains)
    # Equal share of every epoch for each domain, so 2,000 field photos are not
    # drowned out and new classes get seen as often as the old ones.
    weights = [1.0 / domain_sizes[d] for d in domains]
    epoch_size = 2 * len(sets["pd_train"]) + len(sets["ex_train"])
    sampler = WeightedRandomSampler(weights, num_samples=epoch_size, replacement=True)
    train_loader = DataLoader(CachedDataset(train_items, field_train_transforms(img_size)),
                              batch_size=args.batch_size, sampler=sampler, drop_last=True)

    head = final_linear(model)
    head_ids = {id(p) for p in head.parameters()}
    optimizer = torch.optim.AdamW([
        {"params": [p for p in model.parameters() if id(p) not in head_ids], "lr": args.lr},
        {"params": head.parameters(), "lr": args.lr * 5},
    ], weight_decay=1e-4)
    steps = args.epochs * len(train_loader)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=[args.lr, args.lr * 5], total_steps=steps, pct_start=0.15)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

    raw_path = Path(args.out).with_suffix(".raw.pt")
    best_score, best_state, history = -1.0, None, []
    if args.weights:
        best_state = torch.load(args.weights, map_location="cpu", weights_only=True)
        print(f"loaded fine-tuned weights from {args.weights}; skipping training")
    for epoch in range(1, (0 if args.weights else args.epochs) + 1):
        model.train()
        t0, seen, correct, total_loss = time.time(), 0, 0, 0.0
        for x, y in train_loader:
            out = model(x)
            loss = criterion(out, y)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            scheduler.step()
            total_loss += loss.item() * len(y)
            correct += (out.argmax(1) == y).sum().item()
            seen += len(y)

        pd_logits, _, pd_y = collect(model, loader(sets["pd_val"]))
        pv_logits, _, pv_y = collect(model, loader(sets["pv_val"]))
        pd_acc, pv_acc = accuracy(pd_logits, pd_y), accuracy(pv_logits, pv_y)
        score = (pd_acc + pv_acc) / 2  # improve the field without giving up the lab
        history.append({"epoch": epoch, "train_loss": total_loss / seen, "train_acc": correct / seen,
                        "field_val_acc": pd_acc, "lab_val_acc": pv_acc})
        print(f"epoch {epoch}/{args.epochs}  loss {total_loss / seen:.3f}  train {correct / seen:.1%}"
              f"  field-val {pd_acc:.1%}  lab-val {pv_acc:.1%}  ({time.time() - t0:.0f}s)", flush=True)
        if score > best_score:
            best_score = score
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    if not args.weights:
        # Save before any post-processing, so an error below never costs the training run.
        torch.save(best_state, raw_path)
        print(f"saved trained weights to {raw_path}")
    after = report("after")

    # ---- calibration and OOD statistics ------------------------------------
    val_logits, val_feats, val_y = collect(model, loader(val_items))
    temperature = fit_temperature(val_logits, val_y)
    print(f"temperature {temperature:.2f}  ECE {ece(val_logits, val_y):.3f} -> "
          f"{ece(val_logits / temperature, val_y):.3f}")

    # Prototypes come from clean (non-augmented) training images.
    tr_logits, tr_feats, tr_y = collect(model, loader(train_items))
    prototypes = torch.zeros(len(class_names), tr_feats.shape[1])
    for c in range(len(class_names)):
        mask = tr_y == c
        if mask.any():
            prototypes[c] = F.normalize(tr_feats[mask], dim=1).mean(0)
    prototypes = F.normalize(prototypes, dim=1)

    # Thresholds at the 3rd percentile of held-out leaves: at most ~3% of real
    # leaves get flagged by each test.
    val_cos = max_cosine(val_feats, prototypes)
    val_energy = energy(val_logits, temperature)
    cos_thr = float(torch.quantile(val_cos, 0.03))
    energy_thr = float(torch.quantile(val_energy, 0.03))
    in_flag = ((val_cos < cos_thr) | (val_energy < energy_thr)).float().mean().item()
    print(f"OOD thresholds: cosine {cos_thr:.3f}, energy {energy_thr:.2f} "
          f"- flags {in_flag:.1%} of real leaves")

    ood_result = None
    ood_dir = Path(args.ood_dir)
    if ood_dir.is_dir():
        ood_items = cache_all([(p, 0) for p in list_images(ood_dir)])
        if ood_items:
            o_logits, o_feats, _ = collect(model, loader(ood_items))
            o_flag = ((max_cosine(o_feats, prototypes) < cos_thr) |
                      (energy(o_logits, temperature) < energy_thr)).float().mean().item()
            ood_result = {"non_leaf_images": len(ood_items), "flagged": o_flag}
            print(f"OOD check: {o_flag:.1%} of {len(ood_items)} non-leaf photos flagged as unknown")

    # ---- save ---------------------------------------------------------------
    metrics = {
        "val_accuracy": after["pv_val"]["top1"],
        "lab_accuracy": after["pv_val"]["top1"],
        "field_accuracy": after["pd_test"]["top1"],
        "field_top3": after["pd_test"]["top3"],
        "before": {"field_accuracy": before["pd_test"]["top1"], "field_top3": before["pd_test"]["top3"],
                   "lab_accuracy": before["pv_val"]["top1"],
                   "base_val_accuracy": ckpt.get("metrics", {}).get("val_accuracy")},
        "field_test_set": f"PlantDoc test ({len(sets['pd_test'])} images)",
        "lab_test_set": f"PlantVillage sample holdout ({len(sets['pv_val'])} images)",
        "temperature": temperature,
        "ood": {"leaf_flag_rate": in_flag, **(ood_result or {})},
        "finetune": {"epochs": args.epochs, "lr": args.lr, "batch_size": args.batch_size,
                     "plantdoc_train": len(sets["pd_train"]), "plantvillage_train": len(sets["pv_train"]),
                     "extra_train": len(sets["ex_train"]), "history": history},
    }
    save_checkpoint(args.out, model, class_names, arch, img_size, metrics,
                    temperature=temperature,
                    ood={"prototypes": prototypes, "cos_threshold": cos_thr, "energy_threshold": energy_thr})
    Path(args.out).with_suffix(".json").write_text(json.dumps(metrics, indent=2))
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
