"""Verification workflow orchestration controller."""

from __future__ import annotations

import hashlib
import json
import os

from controllers.database_controller import database_controller
from models.verification import Verification
from services.image_utils import ImageUtils, QualityResult
from services.local_model_service import LocalModelService
from utils.licence_manager import LicenceManager
from utils.logger import get_logger
from utils.thread_workers import LocalModelWorker

logger = get_logger("verification_controller")


class VerificationController:
    """Coordinates end to end verification operations."""

    VALID_MODES = {"A_SCREEN", "B_UPLOAD", "B_CAMERA", "C_ADHOC"}

    def __init__(self) -> None:
        self.logger = logger
        self.licence_manager = LicenceManager.get_instance()
        self.database_controller = database_controller

    def start_verification(
        self,
        reference_image_path: str,
        submitted_image_path: str,
        mode: str,
        person_id: int | None = None,
        person_name: str | None = None,
        parent_widget=None,
    ) -> LocalModelWorker | None:
        if not os.path.exists(reference_image_path):
            raise FileNotFoundError(f"Reference image not found: {reference_image_path}")
        if not os.path.exists(submitted_image_path):
            raise FileNotFoundError(f"Submitted image not found: {submitted_image_path}")

        normalized_mode = str(mode or "").strip().upper()
        if normalized_mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported verification mode: {mode}")

        verifications_today = self.database_controller.get_verifications_today_count()
        allowed, message = self.licence_manager.check_verification_limit(verifications_today)
        if not allowed:
            self.logger.info("Verification limit reached for tier %s", self.licence_manager.get_tier())
            self.licence_manager.show_upgrade_prompt(parent_widget, "Unlimited Daily Verifications")
            if message:
                self.logger.warning(message)
            return None

        model_service = LocalModelService()
        model_ready, _message = model_service.ping()
        if not model_ready:
            raise ValueError(
                "The signature verification model is not installed. Please contact your system administrator to install the model file (signverify_model.pth) in the models/ directory."
            )

        self.logger.info(
            "Starting verification mode=%s reference=%s submitted=%s",
            normalized_mode,
            reference_image_path,
            submitted_image_path,
        )

        worker = LocalModelWorker(
            reference_image_path=reference_image_path,
            submitted_image_path=submitted_image_path,
            person_name=person_name or "",
        )
        return worker

    def save_verification_result(
        self,
        result_dict: dict,
        mode: str,
        person_id: int | None = None,
        reference_image_path: str = "",
        submitted_image_path: str = "",
    ) -> Verification:
        verdict = str(
            result_dict.get("verdict")
            or result_dict.get("result")
            or "INCONCLUSIVE"
        ).upper()

        try:
            confidence = float(result_dict.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        reason = str(result_dict.get("reason", "") or "")
        observations = result_dict.get("observations") or {}
        if not isinstance(observations, dict):
            observations = {}

        observations_json = json.dumps(observations, ensure_ascii=False)
        raw_response_json = json.dumps(result_dict, ensure_ascii=False)
        response_hash = hashlib.sha256(raw_response_json.encode("utf-8")).hexdigest()

        verification = self.database_controller.add_verification(
            person_id=person_id,
            mode=mode,
            reference_image_path=reference_image_path,
            submitted_image_path=submitted_image_path,
            verdict=verdict,
            confidence=confidence,
            reason=reason,
            observations_json=observations_json,
            raw_response_json=raw_response_json,
        )

        if not verification.response_hash:
            verification.response_hash = response_hash

        self.logger.info(
            "Verification saved: id=%s, verdict=%s, confidence=%.2f",
            verification.id,
            verdict,
            confidence,
        )
        return verification

    def get_quality_assessment(self, image_path: str) -> QualityResult:
        try:
            return ImageUtils().assess_quality(image_path)
        except Exception as exc:
            self.logger.exception("Failed quality assessment for path: %s", image_path)
            raise RuntimeError(f"Failed to assess image quality: {exc}") from exc


verification_controller = VerificationController()
