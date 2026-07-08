"""Rotating file logging for launcher and engine processes."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from unmouse.config import Settings

LOG_FILENAME = "unmouse.log"
MAX_BYTES = 2_000_000
BACKUP_COUNT = 5


def log_file_path(settings: Settings) -> Path:
    return settings.logs_dir / LOG_FILENAME


def setup_logging(settings: Settings, *, name: str = "unmouse") -> logging.Logger:
    logs_dir = settings.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if settings.debug else logging.INFO
    root = logging.getLogger()
    target = log_file_path(settings)
    has_file_handler = any(
        isinstance(handler, RotatingFileHandler)
        and Path(getattr(handler, "baseFilename", "")) == target
        for handler in root.handlers
    )
    if not has_file_handler:
        handler = RotatingFileHandler(
            target,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"),
        )
        root.addHandler(handler)
    root.setLevel(level)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger
