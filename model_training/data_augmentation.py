"""Online augmentation pipeline for signature verification training."""

from __future__ import annotations

import random
from typing import Tuple

import albumentations as A
import cv2
import numpy as np
from torchvision import transforms


class SaltPepperNoise(A.ImageOnlyTransform):
    """Injects sparse salt and pepper noise."""

    def __init__(self, densities: tuple[float, float] = (0.01, 0.03), always_apply: bool = False, p: float = 0.4):
        super().__init__(always_apply=always_apply, p=p)
        self.densities = densities

    def apply(self, img: np.ndarray, **params) -> np.ndarray:
        density = random.choice(self.densities)
        out = img.copy()

        total_pixels = img.shape[0] * img.shape[1]
        count = int(total_pixels * density)
        if count <= 0:
            return out

        ys = np.random.randint(0, img.shape[0], count)
        xs = np.random.randint(0, img.shape[1], count)

        half = count // 2
        out[ys[:half], xs[:half]] = 0
        out[ys[half:], xs[half:]] = 255
        return out


class InkMorphology(A.ImageOnlyTransform):
    """Applies erosion or dilation to emulate ink thinning or thickening."""

    def __init__(self, mode: str, always_apply: bool = False, p: float = 0.25):
        super().__init__(always_apply=always_apply, p=p)
        if mode not in {"erode", "dilate"}:
            raise ValueError("mode must be 'erode' or 'dilate'")
        self.mode = mode

    def apply(self, img: np.ndarray, **params) -> np.ndarray:
        kernel_size = random.choice([1, 2])
        kernel = np.ones((kernel_size + 1, kernel_size + 1), dtype=np.uint8)
        if self.mode == "erode":
            return cv2.erode(img, kernel, iterations=1)
        return cv2.dilate(img, kernel, iterations=1)


class PaperTextureOverlay(A.ImageOnlyTransform):
    """Adds subtle texture to emulate scanned paper surfaces."""

    def apply(self, img: np.ndarray, **params) -> np.ndarray:
        h, w = img.shape[:2]
        noise = np.random.normal(loc=0.0, scale=8.0, size=(h, w)).astype(np.float32)
        blotch = cv2.GaussianBlur(noise, (0, 0), sigmaX=3.0)
        textured = img.astype(np.float32) + blotch
        return np.clip(textured, 0, 255).astype(np.uint8)


class ScanLineArtifacts(A.ImageOnlyTransform):
    """Adds horizontal scan line artifacts with low amplitude."""

    def apply(self, img: np.ndarray, **params) -> np.ndarray:
        out = img.astype(np.float32)
        h, _ = out.shape[:2]

        line_count = max(1, h // 40)
        for _ in range(line_count):
            y = random.randint(0, h - 1)
            amplitude = random.uniform(-12.0, 12.0)
            thickness = random.choice([1, 1, 2])
            out[y : y + thickness, :] = np.clip(out[y : y + thickness, :] + amplitude, 0, 255)

        return out.astype(np.uint8)


class RandomPaddingCenter(A.ImageOnlyTransform):
    """Adds random white border padding and recentering."""

    def __init__(self, max_padding: int = 15, always_apply: bool = False, p: float = 0.4):
        super().__init__(always_apply=always_apply, p=p)
        self.max_padding = max_padding

    def apply(self, img: np.ndarray, **params) -> np.ndarray:
        top = random.randint(0, self.max_padding)
        bottom = random.randint(0, self.max_padding)
        left = random.randint(0, self.max_padding)
        right = random.randint(0, self.max_padding)
        return cv2.copyMakeBorder(
            img,
            top,
            bottom,
            left,
            right,
            borderType=cv2.BORDER_CONSTANT,
            value=255,
        )


class RandomCropResize(A.ImageOnlyTransform):
    """Crops 90 to 100 percent then restores original size."""

    def __init__(self, crop_ratio_range: Tuple[float, float] = (0.9, 1.0), always_apply: bool = False, p: float = 0.3):
        super().__init__(always_apply=always_apply, p=p)
        self.crop_ratio_range = crop_ratio_range

    def apply(self, img: np.ndarray, **params) -> np.ndarray:
        h, w = img.shape[:2]
        ratio = random.uniform(self.crop_ratio_range[0], self.crop_ratio_range[1])
        ch = max(1, int(h * ratio))
        cw = max(1, int(w * ratio))

        y1 = random.randint(0, max(0, h - ch))
        x1 = random.randint(0, max(0, w - cw))
        cropped = img[y1 : y1 + ch, x1 : x1 + cw]
        return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)


def _build_jpeg_transform() -> A.ImageCompression:
    try:
        return A.ImageCompression(quality_range=(70, 95), p=0.35)
    except TypeError:
        return A.ImageCompression(quality_lower=70, quality_upper=95, p=0.35)


class SignatureAugmentationPipeline:
    """Applies online augmentation independently for each image in a pair."""

    def __init__(self, input_size: tuple[int, int] = (224, 224)) -> None:
        self.input_size = input_size

        self.torch_pre = transforms.Compose(
            [
                transforms.RandomApply(
                    [
                        transforms.RandomAffine(
                            degrees=0,
                            translate=(0.02, 0.02),
                            scale=(0.98, 1.02),
                        )
                    ],
                    p=0.2,
                )
            ]
        )

        self.pipeline = A.Compose(
            [
                A.OneOf(
                    [
                        A.Rotate(limit=(-3, 3), border_mode=cv2.BORDER_CONSTANT, value=255, p=1.0),
                        A.Rotate(limit=(-6, 6), border_mode=cv2.BORDER_CONSTANT, value=255, p=1.0),
                        A.Rotate(limit=(-10, 10), border_mode=cv2.BORDER_CONSTANT, value=255, p=1.0),
                        A.Rotate(limit=(-15, 15), border_mode=cv2.BORDER_CONSTANT, value=255, p=1.0),
                    ],
                    p=0.8,
                ),
                A.OneOf(
                    [
                        A.Affine(scale=(0.85, 0.85), fit_output=False, cval=255, p=1.0),
                        A.Affine(scale=(0.92, 0.92), fit_output=False, cval=255, p=1.0),
                        A.Affine(scale=(1.08, 1.08), fit_output=False, cval=255, p=1.0),
                        A.Affine(scale=(1.15, 1.15), fit_output=False, cval=255, p=1.0),
                    ],
                    p=0.7,
                ),
                A.Affine(
                    translate_percent={"x": (-0.05, 0.05), "y": (-0.03, 0.03)},
                    cval=255,
                    p=0.5,
                ),
                A.Perspective(scale=(0.01, 0.04), pad_val=255, p=0.3),
                A.ElasticTransform(alpha=30, sigma=5, alpha_affine=0, border_mode=cv2.BORDER_CONSTANT, value=255, p=0.4),
                A.OneOf(
                    [
                        A.GaussNoise(var_limit=(9, 9), p=1.0),
                        A.GaussNoise(var_limit=(49, 49), p=1.0),
                        A.GaussNoise(var_limit=(144, 144), p=1.0),
                    ],
                    p=0.6,
                ),
                SaltPepperNoise(p=0.4),
                A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.20, p=0.5),
                A.OneOf(
                    [
                        A.GaussianBlur(blur_limit=(3, 3), p=1.0),
                        A.GaussianBlur(blur_limit=(5, 5), p=1.0),
                    ],
                    p=0.3,
                ),
                _build_jpeg_transform(),
                InkMorphology(mode="erode", p=0.25),
                InkMorphology(mode="dilate", p=0.25),
                PaperTextureOverlay(p=0.20),
                ScanLineArtifacts(p=0.15),
                RandomPaddingCenter(max_padding=15, p=0.4),
                RandomCropResize(crop_ratio_range=(0.9, 1.0), p=0.3),
                A.Resize(height=input_size[0], width=input_size[1]),
            ]
        )

    def __call__(self, image: np.ndarray) -> np.ndarray:
        if image.ndim != 2:
            raise ValueError("SignatureAugmentationPipeline expects grayscale image array")

        pil_ready = transforms.ToPILImage()(image)
        transformed = self.torch_pre(pil_ready)
        image_np = np.array(transformed, dtype=np.uint8)

        augmented = self.pipeline(image=image_np)["image"]
        return augmented.astype(np.uint8)
