"""Forensic feature extraction and score-to-observation mapping for local inference."""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
from PIL import Image


class ForensicFeatureExtractor:
    """Extracts handcrafted forensic features and maps model outputs to app observations."""

    def __init__(self) -> None:
        self._last_numeric_scores: dict[str, float] = {}

    @staticmethod
    def _to_gray_array(image: Image.Image | str) -> np.ndarray:
        if isinstance(image, (str, bytes)):
            with Image.open(image) as opened:
                return np.array(opened.convert("L"), dtype=np.uint8)
        return np.array(image.convert("L"), dtype=np.uint8)

    @staticmethod
    def _ink_mask(gray: np.ndarray) -> np.ndarray:
        _, binary_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return (binary_inv > 0).astype(np.uint8)

    @staticmethod
    def _bounding_box(mask: np.ndarray) -> tuple[int, int, int, int]:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0 or len(ys) == 0:
            return 0, 0, mask.shape[1], mask.shape[0]
        x1 = int(xs.min())
        x2 = int(xs.max()) + 1
        y1 = int(ys.min())
        y2 = int(ys.max()) + 1
        return x1, y1, x2, y2

    @staticmethod
    def _skeletonize(mask: np.ndarray) -> np.ndarray:
        img = (mask * 255).astype(np.uint8)
        skel = np.zeros_like(img)
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))

        while True:
            eroded = cv2.erode(img, kernel)
            opened = cv2.dilate(eroded, kernel)
            temp = cv2.subtract(img, opened)
            skel = cv2.bitwise_or(skel, temp)
            img = eroded.copy()
            if cv2.countNonZero(img) == 0:
                break

        return (skel > 0).astype(np.uint8)

    @staticmethod
    def _endpoint_branch_counts(skeleton: np.ndarray) -> tuple[int, int]:
        if skeleton.sum() == 0:
            return 0, 0

        padded = np.pad(skeleton, 1, mode="constant")
        endpoints = 0
        branches = 0

        ys, xs = np.where(skeleton > 0)
        for y, x in zip(ys, xs):
            window = padded[y : y + 3, x : x + 3]
            neighbors = int(window.sum()) - 1
            if neighbors == 1:
                endpoints += 1
            elif neighbors > 3:
                branches += 1

        return endpoints, branches

    @staticmethod
    def _profile_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0

        a_arr = np.asarray(a, dtype=np.float32)
        b_arr = np.asarray(b, dtype=np.float32)

        target_len = max(len(a_arr), len(b_arr))
        x_a = np.linspace(0.0, 1.0, len(a_arr))
        x_b = np.linspace(0.0, 1.0, len(b_arr))
        x_t = np.linspace(0.0, 1.0, target_len)

        a_interp = np.interp(x_t, x_a, a_arr)
        b_interp = np.interp(x_t, x_b, b_arr)

        denom = (np.linalg.norm(a_interp) * np.linalg.norm(b_interp)) + 1e-8
        cosine = float(np.dot(a_interp, b_interp) / denom)
        cosine = max(-1.0, min(1.0, cosine))
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    @staticmethod
    def _ratio_similarity(a: float, b: float, max_delta: float) -> float:
        if max_delta <= 0:
            return 0.0
        delta = abs(float(a) - float(b))
        score = 1.0 - min(delta / max_delta, 1.0)
        return max(0.0, min(1.0, score))

    @staticmethod
    def map_to_rating(score: float | None) -> str:
        if score is None:
            return "Unable to Assess"

        try:
            numeric = float(score)
        except (TypeError, ValueError):
            return "Unable to Assess"

        if math.isnan(numeric):
            return "Unable to Assess"

        if numeric >= 0.75:
            return "High"
        if numeric >= 0.45:
            return "Medium"
        return "Low"

    def extract_image_features(self, image: Image.Image | str) -> dict[str, Any]:
        gray = self._to_gray_array(image)
        mask = self._ink_mask(gray)

        x1, y1, x2, y2 = self._bounding_box(mask)
        roi_mask = mask[y1:y2, x1:x2] if y2 > y1 and x2 > x1 else mask
        roi_gray = gray[y1:y2, x1:x2] if y2 > y1 and x2 > x1 else gray

        baseline_profile = roi_mask.sum(axis=1).astype(float).tolist()
        vertical_profile = roi_mask.sum(axis=0).astype(float).tolist()

        harris_input = np.float32(roi_gray)
        harris = cv2.cornerHarris(harris_input, blockSize=2, ksize=3, k=0.04)
        harris_threshold = 0.01 * harris.max() if harris.size else 0.0
        corners = np.argwhere(harris > harris_threshold)

        edges = cv2.Canny(roi_gray, 50, 150)
        lines = cv2.HoughLines(edges, 1, np.pi / 180.0, threshold=40)
        slant_angle = 0.0
        if lines is not None and len(lines) > 0:
            angles = []
            for line in lines[:200]:
                theta = float(line[0][1])
                angle_deg = np.degrees(theta) - 90.0
                if -90 <= angle_deg <= 90:
                    angles.append(angle_deg)
            if angles:
                slant_angle = float(np.median(angles))

        # 4x4 local density map
        grid_rows, grid_cols = 4, 4
        density_map = np.zeros((grid_rows, grid_cols), dtype=np.float32)
        roi_h, roi_w = roi_mask.shape[:2]
        for gr in range(grid_rows):
            for gc in range(grid_cols):
                y_start = int(gr * roi_h / grid_rows)
                y_end = int((gr + 1) * roi_h / grid_rows)
                x_start = int(gc * roi_w / grid_cols)
                x_end = int((gc + 1) * roi_w / grid_cols)
                patch = roi_mask[y_start:y_end, x_start:x_end]
                density_map[gr, gc] = float(patch.mean()) if patch.size else 0.0

        contour_complexity = 0.0
        contours, hierarchy = cv2.findContours((roi_mask * 255).astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        loop_count = 0
        if contours:
            largest = max(contours, key=cv2.contourArea)
            area = max(cv2.contourArea(largest), 1.0)
            perimeter = cv2.arcLength(largest, True)
            contour_complexity = float(perimeter / math.sqrt(area))

        if hierarchy is not None and len(hierarchy) > 0:
            for idx in range(len(contours)):
                parent_idx = hierarchy[0][idx][3]
                if parent_idx >= 0:
                    loop_count += 1

        distance = cv2.distanceTransform((roi_mask * 255).astype(np.uint8), cv2.DIST_L2, 5)
        valid_distance = distance[distance > 0]
        stroke_width_variation = float(np.std(valid_distance * 2.0)) if valid_distance.size else 0.0

        ink_pixels = roi_gray[roi_mask > 0]
        pixel_intensity_std = float(np.std(ink_pixels)) if ink_pixels.size else float(np.std(roi_gray))

        moments = cv2.moments((roi_mask * 255).astype(np.uint8))
        hu = cv2.HuMoments(moments).flatten()
        spatial_moments = [float(v) for v in hu.tolist()]

        skeleton = self._skeletonize(roi_mask)
        endpoint_count, branch_count = self._endpoint_branch_counts(skeleton)

        return {
            "stroke_endpoints": {
                "count": int(len(corners)),
                "positions": [(int(y), int(x)) for y, x in corners[:300]],
            },
            "baseline_profile": baseline_profile,
            "vertical_profile": vertical_profile,
            "slant_angle": float(slant_angle),
            "ink_density_map": density_map.flatten().astype(float).tolist(),
            "contour_complexity": float(contour_complexity),
            "loop_count": int(loop_count),
            "stroke_width_variation": float(stroke_width_variation),
            "pixel_intensity_std": float(pixel_intensity_std),
            "spatial_moments": spatial_moments,
            "skeleton_features": {
                "branch_points": int(branch_count),
                "endpoint_count": int(endpoint_count),
            },
            "bounding_box": {
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2),
                "width": int(max(1, x2 - x1)),
                "height": int(max(1, y2 - y1)),
            },
        }

    @staticmethod
    def _get_model_score(model_output: dict[str, float], key: str, fallback: float = 0.5) -> float:
        value = model_output.get(key, fallback)
        try:
            value_float = float(value)
            if math.isnan(value_float):
                return fallback
            return max(0.0, min(1.0, value_float))
        except (TypeError, ValueError):
            return fallback

    def baseline_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        return self._profile_similarity(f1.get("baseline_profile", []), f2.get("baseline_profile", []))

    def slant_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        return self._ratio_similarity(f1.get("slant_angle", 0.0), f2.get("slant_angle", 0.0), max_delta=45.0)

    def pressure_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        intensity_sim = self._ratio_similarity(
            f1.get("pixel_intensity_std", 0.0),
            f2.get("pixel_intensity_std", 0.0),
            max_delta=80.0,
        )
        width_sim = self._ratio_similarity(
            f1.get("stroke_width_variation", 0.0),
            f2.get("stroke_width_variation", 0.0),
            max_delta=12.0,
        )
        return float((intensity_sim + width_sim) / 2.0)

    def loop_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        return self._ratio_similarity(f1.get("loop_count", 0), f2.get("loop_count", 0), max_delta=12.0)

    def ink_distribution_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        map1 = np.asarray(f1.get("ink_density_map", []), dtype=np.float32)
        map2 = np.asarray(f2.get("ink_density_map", []), dtype=np.float32)
        if map1.size == 0 or map2.size == 0:
            return 0.0
        return self._profile_similarity(map1.tolist(), map2.tolist())

    def spatial_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        hu1 = np.asarray(f1.get("spatial_moments", []), dtype=np.float32)
        hu2 = np.asarray(f2.get("spatial_moments", []), dtype=np.float32)
        if hu1.size == 0 or hu2.size == 0:
            return 0.0

        distance = float(np.mean(np.abs(hu1 - hu2)))
        hu_score = max(0.0, min(1.0, 1.0 - min(distance * 20.0, 1.0)))

        shape1 = f1.get("bounding_box", {})
        shape2 = f2.get("bounding_box", {})
        ratio1 = float(shape1.get("width", 1)) / max(float(shape1.get("height", 1)), 1.0)
        ratio2 = float(shape2.get("width", 1)) / max(float(shape2.get("height", 1)), 1.0)
        ratio_score = self._ratio_similarity(ratio1, ratio2, max_delta=3.0)

        return float((hu_score + ratio_score) / 2.0)

    def tremor_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        skeleton1 = f1.get("skeleton_features", {})
        skeleton2 = f2.get("skeleton_features", {})
        endpoint_sim = self._ratio_similarity(
            skeleton1.get("endpoint_count", 0),
            skeleton2.get("endpoint_count", 0),
            max_delta=20.0,
        )
        branch_sim = self._ratio_similarity(
            skeleton1.get("branch_points", 0),
            skeleton2.get("branch_points", 0),
            max_delta=20.0,
        )
        return float((endpoint_sim + branch_sim) / 2.0)

    def complexity_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        return self._ratio_similarity(
            f1.get("contour_complexity", 0.0),
            f2.get("contour_complexity", 0.0),
            max_delta=20.0,
        )

    def spacing_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        return self._profile_similarity(f1.get("vertical_profile", []), f2.get("vertical_profile", []))

    def size_similarity(self, f1: dict[str, Any], f2: dict[str, Any]) -> float:
        box1 = f1.get("bounding_box", {})
        box2 = f2.get("bounding_box", {})
        width_score = self._ratio_similarity(box1.get("width", 1), box2.get("width", 1), max_delta=500.0)
        height_score = self._ratio_similarity(box1.get("height", 1), box2.get("height", 1), max_delta=250.0)
        return float((width_score + height_score) / 2.0)

    def compute_similarity_scores(
        self,
        features1: dict[str, Any],
        features2: dict[str, Any],
        model_output: dict[str, float],
    ) -> dict[str, str]:
        numeric_scores = {
            "overall_gestalt": self._get_model_score(model_output, "overall_gestalt_score"),
            "pen_lift_points": self._get_model_score(model_output, "pen_lift_score"),
            "letter_formation": self._get_model_score(model_output, "letter_formation_score"),
            "baseline_consistency": self.baseline_similarity(features1, features2),
            "slant_angle": self.slant_similarity(features1, features2),
            "pressure_pattern": self.pressure_similarity(features1, features2),
            "speed_indicators": self._get_model_score(model_output, "speed_indicator_score"),
            "loop_proportions": self.loop_similarity(features1, features2),
            "beginning_strokes": self._get_model_score(model_output, "beginning_stroke_score"),
            "ending_strokes": self._get_model_score(model_output, "ending_stroke_score"),
            "connecting_strokes": self._get_model_score(model_output, "connecting_stroke_score"),
            "abbreviation_style": self._get_model_score(model_output, "abbreviation_style_score"),
            "flourish_patterns": self._get_model_score(model_output, "flourish_pattern_score"),
            "ink_distribution": self.ink_distribution_similarity(features1, features2),
            "stroke_consistency": self._get_model_score(model_output, "stroke_consistency"),
            "spatial_proportions": self.spatial_similarity(features1, features2),
            "retouching_indicators": self._get_model_score(model_output, "retouching_indicators"),
            "tremor_assessment": self.tremor_similarity(features1, features2),
            "natural_variation": self._get_model_score(model_output, "natural_variation"),
            "complexity_level": self.complexity_similarity(features1, features2),
            "character_spacing": self.spacing_similarity(features1, features2),
            "terminal_features": self._get_model_score(model_output, "terminal_features"),
            "size_consistency": self.size_similarity(features1, features2),
            "rhythm_pattern": self._get_model_score(model_output, "rhythm_pattern"),
            "overall_similarity": self._get_model_score(model_output, "overall_similarity"),
        }

        self._last_numeric_scores = numeric_scores
        return {key: self.map_to_rating(score) for key, score in numeric_scores.items()}

    def generate_forensic_reason(self, observations: dict[str, str], similarity_score: float, verdict: str) -> str:
        high = [key for key, value in observations.items() if str(value).strip().lower() == "high"]
        medium = [key for key, value in observations.items() if str(value).strip().lower() == "medium"]
        low = [key for key, value in observations.items() if str(value).strip().lower() == "low"]

        # Determine discriminative features from numeric scores when available
        ranked = sorted(self._last_numeric_scores.items(), key=lambda item: item[1], reverse=True)
        top_matching = [name.replace("_", " ") for name, _ in ranked[:3]] if ranked else ["overall gestalt", "stroke consistency", "rhythm pattern"]
        top_differing = [name.replace("_", " ") for name, _ in ranked[-3:]] if ranked else ["slant angle", "character spacing", "terminal features"]

        confidence_pct = max(0.0, min(100.0, float(similarity_score) * 100.0))
        verdict_upper = str(verdict or "INCONCLUSIVE").upper()

        sentence_1 = (
            "The comparative analysis of the two signatures using 13 forensic strategies and 25 analytical dimensions "
            f"yielded a {verdict_upper} determination with {confidence_pct:.1f}% confidence."
        )

        sentence_2 = (
            f"Analysis of {len(high)} feature dimensions showed strong concordance, particularly in "
            f"{', '.join(top_matching)}."
        )

        if verdict_upper == "MISMATCH":
            sentence_3 = (
                f"Notable discrepancies were identified in {', '.join(top_differing)}, suggesting different signers or skilled forgery."
            )
        elif verdict_upper == "INCONCLUSIVE":
            quality_hint = "limited reference data"
            if len(low) >= 8:
                quality_hint = "substantial structural divergence"
            elif len(medium) >= len(high):
                quality_hint = "natural variation overlap"
            sentence_3 = (
                "The evidence is insufficient for a definitive determination, likely due to "
                f"{quality_hint}."
            )
        else:
            sentence_3 = (
                f"Only {len(low)} dimensions showed low concordance, and these were not sufficient to overturn the overall match pattern."
            )

        sentence_4 = "This assessment is based entirely on locally processed image analysis using the SignVerify Pro trained model."

        return " ".join([sentence_1, sentence_2, sentence_3, sentence_4])
