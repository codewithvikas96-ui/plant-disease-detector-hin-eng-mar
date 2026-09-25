"""Model definition shared by the Colab training notebook and the inference server.

Keeping the architecture in one place means the checkpoint saved on Colab always
loads cleanly here. If you change the architecture, retrain — the checkpoint
stores its own `arch` string and the server refuses to load a mismatch.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torchvision import models, transforms

# MobileNetV3-Large: ~5.4 M parameters, ~22 MB checkpoint, runs in well under a
# second per image on a laptop CPU. That matters here — the demo machine has no GPU.
DEFAULT_ARCH = "mobilenet_v3_large"
IMG_SIZE = 224

# ImageNet statistics, because we fine-tune from ImageNet weights.
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def build_model(num_classes: int, arch: str = DEFAULT_ARCH, pretrained: bool = True) -> nn.Module:
    """Return a torchvision backbone with its classifier resized to `num_classes`."""
    if arch == "mobilenet_v3_large":
        weights = models.MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None
        model = models.mobilenet_v3_large(weights=weights)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, num_classes)
    elif arch == "efficientnet_b0":
        weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        model = models.efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)
    elif arch == "resnet18":
        weights = models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        model = models.resnet18(weights=weights)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    else:
        raise ValueError(f"Unknown architecture: {arch}")
    return model


def train_transforms(img_size: int = IMG_SIZE) -> transforms.Compose:
    """Augmentation for training.

    PlantVillage photos are all shot on a uniform background in good light, while
    a farmer's phone photo is not. The colour jitter and rotation below are what
    stop the model from falling apart on real field images.
    """
    return transforms.Compose([
        transforms.RandomResizedCrop(img_size, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(30),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
        transforms.RandomErasing(p=0.2, scale=(0.02, 0.1)),
    ])


def eval_transforms(img_size: int = IMG_SIZE) -> transforms.Compose:
    """Deterministic pipeline used for validation and for live inference."""
    return transforms.Compose([
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])


def final_linear(model: nn.Module) -> nn.Linear:
    """The classification layer, whatever the backbone."""
    for module in reversed(list(model.modules())):
        if isinstance(module, nn.Linear):
            return module
    raise ValueError("model has no Linear layer")


def cam_layer(model: nn.Module, arch: str) -> nn.Module:
    """Last convolutional block — the layer Grad-CAM explains.

    It is the deepest layer that still has a spatial map (7x7 at 224 px), so it
    is where 'which part of the leaf mattered' can still be read off.
    """
    if arch in ("mobilenet_v3_large", "efficientnet_b0"):
        return model.features[-1]
    if arch == "resnet18":
        return model.layer4
    raise ValueError(f"Unknown architecture: {arch}")


class FeatureTap:
    """Captures the input to the final Linear layer (the penultimate embedding).

    Used for out-of-distribution detection: a photo of a hand still gets a
    softmax over 38 diseases, but its embedding sits far from every class.
    """

    def __init__(self, model: nn.Module) -> None:
        self.features: torch.Tensor | None = None
        self._handle = final_linear(model).register_forward_hook(self._hook)

    def _hook(self, _module, inputs, _output) -> None:
        self.features = inputs[0]

    def close(self) -> None:
        self._handle.remove()


def save_checkpoint(path, model: nn.Module, class_names: list[str], arch: str,
                    img_size: int, metrics: dict, **extra) -> None:
    """Write a self-describing checkpoint the server can load without extra files.

    `extra` carries optional calibration data such as `temperature` and `ood`.
    """
    torch.save({
        "arch": arch,
        "img_size": img_size,
        "class_names": class_names,
        "state_dict": model.state_dict(),
        "metrics": metrics,
        **extra,
    }, path)
