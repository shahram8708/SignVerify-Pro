"""Validation helpers for user input and file checks."""

from __future__ import annotations

import re
from pathlib import Path

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def validate_name(name: str) -> tuple[bool, str]:
    candidate = (name or "").strip()
    if not candidate:
        return False, "Name is required"
    if len(candidate) < 2:
        return False, "Name must be at least 2 characters"
    if len(candidate) > 100:
        return False, "Name must be at most 100 characters"
    if not re.fullmatch(r"[A-Za-z\s\-']+", candidate):
        return False, "Name can only contain letters, spaces, hyphens, and apostrophes"
    return True, ""


def validate_image_path(path: str) -> tuple[bool, str]:
    if not path:
        return False, "Image path is required"

    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return False, "Image file does not exist"

    if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False, "Image must be a PNG or JPEG file"

    file_size = file_path.stat().st_size
    if file_size > MAX_IMAGE_SIZE_BYTES:
        return False, "Image file must be smaller than 10MB"

    return True, ""


def validate_api_key(key: str) -> tuple[bool, str]:
    candidate = (key or "").strip()
    if not candidate:
        return False, "API key is required"
    if len(candidate) < 20:
        return False, "API key must be at least 20 characters"
    if not candidate.startswith("AIza"):
        return False, "API key must start with 'AIza'"
    return True, ""


def validate_confidence(value: float) -> tuple[bool, str]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False, "Confidence must be a number"

    if 0.0 <= numeric <= 1.0:
        return True, ""
    return False, "Confidence must be between 0.0 and 1.0"


def validate_file_mime(path: str) -> tuple[bool, str]:
    if not path:
        return False, "Image path is required"

    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return False, "Image file does not exist"

    with file_path.open("rb") as file:
        header = file.read(12)

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, ""

    if header.startswith(b"\xff\xd8\xff"):
        return True, ""

    return False, "File content is not a valid PNG or JPEG image"
