"""Controller for persisted application settings."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, text

from config import BASE_DIR
from database.db_manager import SessionLocal
from models.settings_model import Setting
from services import encryption_service
from utils.logger import get_logger

logger = get_logger(__name__)


class SettingsController:
    """Encapsulates settings read and write operations."""

    VALID_LICENCE_TIERS = {"FREE", "PROFESSIONAL", "ENTERPRISE"}

    def get(self, key: str, default=None):
        try:
            with SessionLocal() as session:
                setting = session.get(Setting, key)
                if setting is None:
                    return os.getenv(key.upper(), default)

                if setting.is_encrypted == 1 and setting.value:
                    return encryption_service.decrypt(setting.value)

                return setting.value if setting.value is not None else default
        except Exception as exc:
            logger.exception("Failed to read setting")
            raise RuntimeError(f"Failed to read setting '{key}': {exc}") from exc

    def set(self, key: str, value: str, encrypted: bool = False) -> None:
        try:
            to_store = encryption_service.encrypt(value) if encrypted and value else value
            encrypted_flag = 1 if encrypted else 0
            with SessionLocal() as session:
                session.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO settings (key, value, is_encrypted, updated_at)
                        VALUES (:key, :value, :is_encrypted, :updated_at)
                        """
                    ),
                    {
                        "key": key,
                        "value": to_store,
                        "is_encrypted": encrypted_flag,
                        "updated_at": datetime.utcnow(),
                    },
                )
                session.commit()
        except Exception as exc:
            logger.exception("Failed to save setting")
            raise RuntimeError(f"Failed to save setting '{key}': {exc}") from exc

    def get_all(self) -> dict[str, str | None]:
        settings_map: dict[str, str | None] = {}
        try:
            with SessionLocal() as session:
                rows = session.scalars(select(Setting)).all()
                for row in rows:
                    if row.is_encrypted == 1 and row.value:
                        settings_map[row.key] = encryption_service.decrypt(row.value)
                    else:
                        settings_map[row.key] = row.value
            return settings_map
        except Exception as exc:
            logger.exception("Failed to load settings")
            raise RuntimeError(f"Failed to load settings: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            with SessionLocal() as session:
                record = session.get(Setting, key)
                if record is not None:
                    session.delete(record)
                    session.commit()
        except Exception as exc:
            logger.exception("Failed to delete setting")
            raise RuntimeError(f"Failed to delete setting '{key}': {exc}") from exc

    def get_model_path(self) -> str:
        default_path = str((Path(BASE_DIR) / "models" / "signverify_model.pth").resolve())
        return str(self.get("model_path", default_path) or default_path)

    def set_model_path(self, path: str) -> None:
        self.set("model_path", str(path or "").strip())

    def get_inference_device(self) -> str:
        value = str(self.get("inference_device", "auto") or "auto").strip().lower()
        if value not in {"auto", "cpu", "cuda"}:
            return "auto"
        return value

    def set_inference_device(self, device: str) -> None:
        normalized = str(device or "auto").strip().lower()
        if normalized not in {"auto", "cpu", "cuda"}:
            normalized = "auto"
        self.set("inference_device", normalized)

    def get_capture_mode(self) -> str:
        return str(self.get("capture_mode", "full_screen") or "full_screen")

    def get_camera_index(self) -> int:
        value = self.get("camera_index", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def get_detection_sensitivity(self) -> float:
        value = self.get("detection_sensitivity", 0.5)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.5

    def get_licence_tier(self) -> str:
        fallback_tier = os.getenv("LICENCE_TIER", "FREE")
        tier = str(self.get("licence_tier", fallback_tier) or fallback_tier).strip().upper()
        if tier not in self.VALID_LICENCE_TIERS:
            return "FREE"
        return tier

    def set_licence_tier(self, tier: str) -> None:
        normalized_tier = str(tier or "").strip().upper()
        if normalized_tier not in self.VALID_LICENCE_TIERS:
            raise ValueError(
                "Invalid licence tier. Allowed values: FREE, PROFESSIONAL, ENTERPRISE"
            )

        self.set("licence_tier", normalized_tier)
        os.environ["LICENCE_TIER"] = normalized_tier


settings_controller = SettingsController()
