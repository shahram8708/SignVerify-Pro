"""Local offline model service for signature verification."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from config import BASE_DIR
from controllers.settings_controller import settings_controller
from model_training.forensic_feature_extractor import ForensicFeatureExtractor
from services.image_utils import ImageUtils
from utils.logger import get_logger


class LocalModelService:
    """Loads and runs local Siamese model inference with forensic mapping."""

    def __init__(self) -> None:
        self.logger = get_logger("local_model_service")
        self.model = None
        self.threshold = 0.5

        inference_pref = str(settings_controller.get("inference_device", "auto") or "auto").strip().lower()
        if inference_pref == "cpu":
            self.device = "cpu"
        elif inference_pref == "cuda":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        default_path = str(BASE_DIR / "models" / "signverify_model.pth")
        self.model_path = str(settings_controller.get("model_path", default_path) or default_path)
        self.forensic_extractor = ForensicFeatureExtractor()

    @staticmethod
    def _temperature_scale(probability: float, temperature: float = 1.5) -> float:
        probability = min(max(float(probability), 1e-6), 1.0 - 1e-6)
        logit = math.log(probability / (1.0 - probability))
        scaled = 1.0 / (1.0 + math.exp(-(logit / temperature)))
        return float(min(max(scaled, 0.0), 1.0))

    def load_model(self) -> bool:
        model_path = Path(self.model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found at {self.model_path}. Please train the model first using model_training/train.py or download the pre-trained model."
            )

        from model_training.model_architecture import SiameseSignatureNet

        checkpoint = torch.load(model_path, map_location=self.device)
        if "model_state_dict" not in checkpoint:
            raise RuntimeError("Invalid model checkpoint: missing model_state_dict")

        model = SiameseSignatureNet()
        model.load_state_dict(checkpoint["model_state_dict"])

        self.threshold = float(checkpoint.get("optimal_threshold", 0.5))
        model.eval()
        model.to(self.device)
        self.model = model

        model_arch = str(checkpoint.get("model_architecture", "SiameseSignatureNet_ResNet50"))
        training_eer = float(checkpoint.get("training_eer", 0.0))
        self.logger.info(
            "Model loaded successfully: %s, EER=%.2f%%, threshold=%.3f",
            model_arch,
            training_eer * 100.0,
            self.threshold,
        )
        return True

    def _preprocess_image(self, image_path: str) -> torch.Tensor:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            gray = gray.resize((224, 224), Image.Resampling.LANCZOS)

        image_array = np.array(gray, dtype=np.float32) / 255.0
        image_tensor = torch.from_numpy(image_array)
        image_tensor = image_tensor.unsqueeze(0).unsqueeze(0).float().to(self.device)
        return image_tensor

    def _extract_forensic_scores(self, forensic_output: dict[str, torch.Tensor]) -> dict[str, float]:
        parsed: dict[str, float] = {}
        for key, value in forensic_output.items():
            if torch.is_tensor(value):
                parsed[key] = float(value.detach().view(-1)[0].cpu().item())
            else:
                parsed[key] = float(value)
        return parsed

    def verify_signatures(self, reference_image_path: str, submitted_image_path: str, person_name: str = None) -> dict:
        _ = person_name
        start_time = time.perf_counter()

        try:
            if self.model is None:
                self.load_model()

            if not os.path.exists(reference_image_path):
                raise FileNotFoundError(f"Reference image not found: {reference_image_path}")
            if not os.path.exists(submitted_image_path):
                raise FileNotFoundError(f"Submitted image not found: {submitted_image_path}")

            image_utils = ImageUtils()
            reference_quality = image_utils.assess_quality(reference_image_path)
            submitted_quality = image_utils.assess_quality(submitted_image_path)

            image1 = self._preprocess_image(reference_image_path)
            image2 = self._preprocess_image(submitted_image_path)

            with torch.no_grad():
                emb1 = self.model.branch(image1)
                emb2 = self.model.branch(image2)

                similarity = float(self.model.similarity_head(emb1, emb2).view(-1)[0].item())
                pair_features = self.model.similarity_head.build_pair_features(emb1, emb2)
                forensic_output = self.model.forensic_head(pair_features)

            forensic_scores = self._extract_forensic_scores(forensic_output)

            features1 = self.forensic_extractor.extract_image_features(reference_image_path)
            features2 = self.forensic_extractor.extract_image_features(submitted_image_path)
            observations = self.forensic_extractor.compute_similarity_scores(features1, features2, forensic_scores)

            confidence = self._temperature_scale(similarity, temperature=1.5)
            if confidence >= self.threshold:
                verdict = "MATCH"
            elif confidence >= (self.threshold * 0.75):
                verdict = "INCONCLUSIVE"
            else:
                verdict = "MISMATCH"

            reason = self.forensic_extractor.generate_forensic_reason(observations, confidence, verdict)

            elapsed = time.perf_counter() - start_time
            self.logger.info(
                "Verification complete: verdict=%s, confidence=%.3f, device=%s, time=%.2fs",
                verdict,
                confidence,
                self.device,
                elapsed,
            )

            return {
                "verdict": verdict,
                "confidence": round(confidence, 4),
                "reason": reason,
                "observations": observations,
                "model_used": "SignVerify-SiameseResNet50-v1.0",
                "raw_response": json.dumps(forensic_scores),
                "inference_device": self.device,
                "threshold_used": self.threshold,
                "analysis_time_sec": round(elapsed, 3),
                "reference_quality": reference_quality._asdict(),
                "submitted_quality": submitted_quality._asdict(),
            }

        except Exception as exc:
            raise RuntimeError(f"Local model inference failed: {exc}") from exc

    def ping(self) -> tuple[bool, str]:
        model_file = Path(self.model_path)
        if not model_file.exists():
            return (
                False,
                f"Model file not found at {self.model_path}. Run model_training/train.py to train the model.",
            )

        metadata_path = Path(BASE_DIR) / "models" / "model_metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                architecture = str(metadata.get("model_architecture", "SiameseSignatureNet_ResNet50"))
                eer = float(metadata.get("training_eer", 0.0)) * 100.0
                return True, f"Model ready: {architecture}, trained EER: {eer:.2f}%"
            except Exception:
                pass

        try:
            checkpoint = torch.load(model_file, map_location="cpu")
            architecture = str(checkpoint.get("model_architecture", "SiameseSignatureNet_ResNet50"))
            eer = float(checkpoint.get("training_eer", 0.0)) * 100.0
            return True, f"Model ready: {architecture}, trained EER: {eer:.2f}%"
        except Exception as exc:
            return False, f"Model file exists but could not be loaded: {exc}"

    def get_model_info(self) -> dict[str, Any]:
        metadata_path = Path(BASE_DIR) / "models" / "model_metadata.json"
        if metadata_path.exists():
            return json.loads(metadata_path.read_text(encoding="utf-8"))

        model_file = Path(self.model_path)
        if not model_file.exists():
            return {
                "model_architecture": "SiameseSignatureNet_ResNet50",
                "training_eer": None,
                "training_date": None,
                "datasets_used": [],
                "total_training_pairs": 0,
                "model_version": "1.0.0",
            }

        checkpoint = torch.load(model_file, map_location="cpu")
        return {
            "model_architecture": checkpoint.get("model_architecture", "SiameseSignatureNet_ResNet50"),
            "training_eer": checkpoint.get("training_eer", None),
            "training_date": checkpoint.get("training_date", None),
            "datasets_used": checkpoint.get("datasets_used", []),
            "total_training_pairs": checkpoint.get("total_training_pairs", 0),
            "model_version": checkpoint.get("model_version", "1.0.0"),
            "optimal_threshold": checkpoint.get("optimal_threshold", self.threshold),
        }
