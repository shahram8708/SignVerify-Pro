"""Centralized logging utilities."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LOG_FILE_PATH

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


class SensitiveDataFilter(logging.Filter):
    """Prevents accidental logging of secrets or binary payloads."""

    forbidden_fragments = (
        "AIza",
        "gemini_api_key",
        "thumbnail_blob",
        "decrypted",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        lowered = message.lower()
        for fragment in self.forbidden_fragments:
            if fragment.lower() in lowered:
                return False
        return True


_handlers_cache: tuple[logging.Handler, logging.Handler] | None = None


def _build_handlers() -> tuple[logging.Handler, logging.Handler]:
    global _handlers_cache
    if _handlers_cache is not None:
        return _handlers_cache

    log_dir = Path(LOG_FILE_PATH).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)
    sensitive_filter = SensitiveDataFilter()

    file_handler = RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(sensitive_filter)

    _handlers_cache = (file_handler, stream_handler)
    return _handlers_cache


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with rotating file and console handlers."""
    logger = logging.getLogger(name)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    file_handler, stream_handler = _build_handlers()
    if file_handler not in logger.handlers:
        logger.addHandler(file_handler)
    if stream_handler not in logger.handlers:
        logger.addHandler(stream_handler)

    logger.propagate = False
    return logger
