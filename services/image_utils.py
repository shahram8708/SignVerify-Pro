"""Image processing helpers for quality checks, encoding, and UI rendering."""

from __future__ import annotations

import base64
import io
import uuid
from collections import namedtuple
from pathlib import Path

import numpy as np
from PIL import Image
from PyQt6.QtGui import QImage, QPixmap

from config import APP_DATA_DIR
from utils.logger import get_logger

QualityResult = namedtuple(
    "QualityResult",
    [
        "resolution",
        "contrast",
        "ink_coverage",
        "overall",
        "resolution_detail",
        "contrast_detail",
        "ink_coverage_detail",
    ],
)


class ImageUtils:
    """Utility class for image quality, conversion, and API preparation."""

    _RATING_RANK = {"Low": 0, "Medium": 1, "High": 2}

    def __init__(self) -> None:
        self.logger = get_logger("image_utils")

    def assess_quality(self, image_path: str) -> QualityResult:
        try:
            with Image.open(image_path) as opened:
                img = opened.convert("RGB")

            resolution, resolution_detail = self._check_resolution(img)
            contrast, contrast_detail = self._check_contrast(img)
            ink_coverage, ink_coverage_detail = self._check_ink_coverage(img)

            overall = min(
                [resolution, contrast, ink_coverage],
                key=lambda rating: self._RATING_RANK.get(rating, 0),
            )

            return QualityResult(
                resolution=resolution,
                contrast=contrast,
                ink_coverage=ink_coverage,
                overall=overall,
                resolution_detail=resolution_detail,
                contrast_detail=contrast_detail,
                ink_coverage_detail=ink_coverage_detail,
            )
        except Exception as exc:
            self.logger.exception("Failed to assess image quality: %s", image_path)
            raise RuntimeError(f"Failed to assess image quality for '{image_path}': {exc}") from exc

    def _check_resolution(self, img: Image.Image) -> tuple[str, str]:
        try:
            width, height = img.size
            if width < 100 or height < 30:
                return "Low", f"Very low resolution ({width}×{height}px) — results may be unreliable"
            if width < 200 or height < 60:
                return "Medium", f"Moderate resolution ({width}×{height}px) — acceptable for verification"
            return "High", f"Good resolution ({width}×{height}px) — suitable for forensic analysis"
        except Exception as exc:
            self.logger.exception("Resolution check failed")
            raise RuntimeError(f"Failed to check image resolution: {exc}") from exc

    def _check_contrast(self, img: Image.Image) -> tuple[str, str]:
        try:
            gray = img.convert("L")
            pixel_array = np.asarray(gray, dtype=np.float32)
            std_dev = float(np.std(pixel_array))

            if std_dev < 30.0:
                return "Low", f"Low contrast (σ={std_dev:.1f}) — image appears washed out or overexposed"
            if std_dev <= 60.0:
                return "Medium", f"Moderate contrast (σ={std_dev:.1f}) — acceptable visibility"
            return "High", f"Strong contrast (σ={std_dev:.1f}) — ink strokes clearly visible"
        except Exception as exc:
            self.logger.exception("Contrast check failed")
            raise RuntimeError(f"Failed to check image contrast: {exc}") from exc

    def _check_ink_coverage(self, img: Image.Image) -> tuple[str, str]:
        try:
            gray = img.convert("L")
            pixel_array = np.asarray(gray, dtype=np.uint8)

            total_pixels = int(pixel_array.size)
            if total_pixels <= 0:
                return "Low", "Very low ink coverage (0.0%) — image may be blank or nearly empty"

            dark_pixels = int(np.sum(pixel_array < 200))
            ink_pct = (dark_pixels / total_pixels) * 100.0

            if ink_pct < 2.0:
                return "Low", f"Very low ink coverage ({ink_pct:.1f}%) — image may be blank or nearly empty"
            if ink_pct > 25.0:
                return "Low", f"Excessively high ink coverage ({ink_pct:.1f}%) — may not be a signature"
            if ink_pct <= 8.0:
                return "High", f"Normal signature ink density ({ink_pct:.1f}%)"
            return "Medium", f"Dense ink coverage ({ink_pct:.1f}%) — possibly a complex signature or stamp"
        except Exception as exc:
            self.logger.exception("Ink coverage check failed")
            raise RuntimeError(f"Failed to check image ink coverage: {exc}") from exc

    def image_to_base64(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read())
            return encoded.decode("utf-8")
        except Exception as exc:
            self.logger.exception("Failed to encode image to base64 string: %s", image_path)
            raise RuntimeError(f"Failed to encode image to base64 string for '{image_path}': {exc}") from exc

    def image_to_base64_bytes(self, image_path: str) -> bytes:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read())
        except Exception as exc:
            self.logger.exception("Failed to encode image to base64 bytes: %s", image_path)
            raise RuntimeError(f"Failed to encode image to base64 bytes for '{image_path}': {exc}") from exc

    def resize_for_api(self, image_path: str, max_width: int = 1024, max_height: int = 512) -> str:
        try:
            with Image.open(image_path) as opened:
                img = opened.convert("RGB")
                width, height = img.size

                if width <= max_width and height <= max_height:
                    return image_path

                ratio = min(max_width / float(width), max_height / float(height))
                new_size = (
                    max(1, int(round(width * ratio))),
                    max(1, int(round(height * ratio))),
                )

                resized = img.resize(new_size, Image.Resampling.LANCZOS)

                temp_dir = APP_DATA_DIR / "temp"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_path = temp_dir / f"{uuid.uuid4().hex}.png"
                resized.save(temp_path, format="PNG")

            return str(temp_path)
        except Exception as exc:
            self.logger.exception("Failed to resize image for API: %s", image_path)
            raise RuntimeError(f"Failed to resize image for API for '{image_path}': {exc}") from exc

    def generate_thumbnail(self, image_path: str, width: int = 100, height: int = 40) -> bytes:
        try:
            with Image.open(image_path) as opened:
                img = opened.convert("RGB")
                img.thumbnail((width, height), Image.Resampling.LANCZOS)

                stream = io.BytesIO()
                img.save(stream, format="JPEG", quality=85)
                return stream.getvalue()
        except Exception as exc:
            self.logger.exception("Failed to generate thumbnail: %s", image_path)
            raise RuntimeError(f"Failed to generate thumbnail for '{image_path}': {exc}") from exc

    def pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        try:
            rgb_image = pil_image.convert("RGB")
            width, height = rgb_image.size
            raw_data = rgb_image.tobytes("raw", "RGB")

            qimage = QImage(
                raw_data,
                width,
                height,
                width * 3,
                QImage.Format.Format_RGB888,
            ).copy()
            return QPixmap.fromImage(qimage)
        except Exception as exc:
            self.logger.exception("Failed to convert PIL image to QPixmap")
            raise RuntimeError(f"Failed to convert PIL image to QPixmap: {exc}") from exc
