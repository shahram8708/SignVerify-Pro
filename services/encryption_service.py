"""Encryption helpers for sensitive settings values."""

from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config import APP_DATA_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


def get_machine_guid() -> str:
    """Get a stable machine identifier for key derivation."""
    try:
        if os.name == "nt":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                value = str(guid).strip()
                if not value:
                    raise RuntimeError("Machine GUID is empty")
                return value

        machine_id_path = Path(APP_DATA_DIR) / ".machine_id"
        if machine_id_path.exists():
            value = machine_id_path.read_text(encoding="utf-8").strip()
            if value:
                return value

        generated = str(uuid.uuid4())
        machine_id_path.parent.mkdir(parents=True, exist_ok=True)
        machine_id_path.write_text(generated, encoding="utf-8")
        return generated
    except Exception as exc:
        logger.exception("Unable to resolve machine identifier")
        raise RuntimeError(f"Unable to resolve machine identifier: {exc}") from exc


def derive_key(salt: str) -> bytes:
    """Derive a 32-byte key from machine identity and provided salt."""
    try:
        if not salt:
            raise ValueError("APP_SECRET_SALT is required")

        machine_guid = get_machine_guid().encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode("utf-8"),
            iterations=100000,
        )
        return kdf.derive(machine_guid)
    except Exception as exc:
        logger.exception("Key derivation failed")
        raise RuntimeError(f"Key derivation failed: {exc}") from exc


def _fernet_instance() -> Fernet:
    salt = os.getenv("APP_SECRET_SALT", "signverifypro_unique_salt_2024")
    key_bytes = derive_key(salt)
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext and return URL-safe token string."""
    try:
        if plaintext is None:
            raise ValueError("Plaintext cannot be None")

        token = _fernet_instance().encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")
    except Exception as exc:
        logger.exception("Encryption failed")
        raise RuntimeError(f"Encryption failed: {exc}") from exc


def decrypt(ciphertext: str) -> str:
    """Decrypt token string and return plaintext."""
    try:
        if not ciphertext:
            return ""

        plaintext = _fernet_instance().decrypt(ciphertext.encode("utf-8"))
        return plaintext.decode("utf-8")
    except InvalidToken as exc:
        logger.exception("Decryption failed due to invalid token")
        raise ValueError(
            "Failed to decrypt value. The token may be invalid for this machine or salt."
        ) from exc
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("Decryption failed")
        raise ValueError(f"Failed to decrypt value: {exc}") from exc
