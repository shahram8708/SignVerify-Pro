"""OpenCV based signature detector."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import QRect

from controllers.settings_controller import settings_controller
from utils.logger import get_logger


class SignatureDetector:
    """Detects likely signature regions from screenshots or document images."""

    def __init__(self, sensitivity: float | None = None) -> None:
        self.logger = get_logger("signature_detector")

        if sensitivity is None:
            sensitivity = settings_controller.get_detection_sensitivity()

        try:
            sensitivity_value = float(sensitivity)
        except (TypeError, ValueError):
            sensitivity_value = 0.5

        self.sensitivity = max(0.0, min(1.0, sensitivity_value))

        computed_min_area = int(800 - (self.sensitivity * 400))
        self.min_area = max(200, min(2000, computed_min_area))
        self.max_area_ratio = 0.30

        try:
            self.aspect_ratio_min = float(settings_controller.get("aspect_ratio_min", "1.5") or "1.5")
        except (TypeError, ValueError):
            self.aspect_ratio_min = 1.5

        try:
            self.aspect_ratio_max = float(settings_controller.get("aspect_ratio_max", "8.0") or "8.0")
        except (TypeError, ValueError):
            self.aspect_ratio_max = 8.0

        self.threshold_block_size = 11
        if self.threshold_block_size % 2 == 0:
            self.threshold_block_size += 1
        self.threshold_c = 2

    def detect(self, pil_image: Image.Image) -> list[dict]:
        rgb_array = np.array(pil_image.convert("RGB"))
        bgr_image = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)

        image_height, image_width = gray.shape
        total_pixels = image_width * image_height
        self.logger.info("Detection started on %sx%s image", image_width, image_height)

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        thresh = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self.threshold_block_size,
            self.threshold_c,
        )

        kernel = np.ones((3, 3), np.uint8)
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(closed, connectivity=8)

        candidates: list[dict] = []
        for index in range(1, num_labels):
            x = int(stats[index, cv2.CC_STAT_LEFT])
            y = int(stats[index, cv2.CC_STAT_TOP])
            w = int(stats[index, cv2.CC_STAT_WIDTH])
            h = int(stats[index, cv2.CC_STAT_HEIGHT])
            area = int(stats[index, cv2.CC_STAT_AREA])

            if h <= 0:
                continue

            if area < self.min_area:
                continue

            if area > total_pixels * self.max_area_ratio:
                continue

            aspect = w / float(h)
            if aspect < self.aspect_ratio_min or aspect > self.aspect_ratio_max:
                continue

            if w < 50:
                continue

            candidates.append(
                {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "area": area,
                    "aspect": aspect,
                }
            )

        if not candidates:
            self.logger.info("No signature candidates found — manual crop required")
            return []

        scored_candidates: list[dict] = []
        for candidate in candidates:
            x = int(candidate["x"])
            y = int(candidate["y"])
            w = int(candidate["width"])
            h = int(candidate["height"])
            aspect = float(candidate["aspect"])

            roi = closed[y : y + h, x : x + w]
            roi_pixels = max(1, w * h)
            ink_pixels = cv2.countNonZero(roi)
            density = ink_pixels / float(roi_pixels)

            if 0.05 <= density <= 0.20:
                ink_density_score = 1.0
            elif 0.035 <= density <= 0.30:
                ink_density_score = 0.5
            else:
                ink_density_score = 0.2

            aspect_ratio_score = max(0.0, min(1.0, 1.0 - abs(aspect - 4.5) / 4.5))

            vertical_position_ratio = (y + (h / 2.0)) / float(max(1, image_height))
            vertical_position_score = min(1.0, vertical_position_ratio * 1.5)

            size_ratio = (w * h) / float(max(1, total_pixels))
            size_score = min(1.0, size_ratio * 20.0)

            score = (
                0.40 * ink_density_score
                + 0.25 * aspect_ratio_score
                + 0.20 * vertical_position_score
                + 0.15 * size_score
            )

            scored_candidates.append(
                {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "score": float(max(0.0, min(1.0, score))),
                }
            )

        scored_candidates.sort(key=lambda item: float(item["score"]), reverse=True)
        top_candidates = scored_candidates[:3]

        results: list[dict] = []
        padding_px = 8
        for rank, candidate in enumerate(top_candidates, start=1):
            x = int(candidate["x"])
            y = int(candidate["y"])
            w = int(candidate["width"])
            h = int(candidate["height"])

            padded_x = max(0, x - padding_px)
            padded_y = max(0, y - padding_px)
            padded_w = min(image_width - padded_x, w + (2 * padding_px))
            padded_h = min(image_height - padded_y, h + (2 * padding_px))

            results.append(
                {
                    "x": int(padded_x),
                    "y": int(padded_y),
                    "width": int(max(1, padded_w)),
                    "height": int(max(1, padded_h)),
                    "score": float(candidate["score"]),
                    "rank": rank,
                }
            )

        self.logger.info("Detection complete: %s candidates found", len(results))
        return results

    def crop_region(self, pil_image: Image.Image, x: int, y: int, width: int, height: int) -> Image.Image:
        image_width, image_height = pil_image.size

        if width <= 0 or height <= 0:
            raise ValueError("Crop width and height must be greater than zero")
        if x < 0 or y < 0:
            raise ValueError("Crop origin cannot be negative")
        if x + width > image_width or y + height > image_height:
            raise ValueError("Crop bounds exceed image dimensions")

        return pil_image.crop((x, y, x + width, y + height))

    def detection_to_qrect(self, detection: dict) -> QRect:
        return QRect(
            int(detection.get("x", 0)),
            int(detection.get("y", 0)),
            int(detection.get("width", 0)),
            int(detection.get("height", 0)),
        )
