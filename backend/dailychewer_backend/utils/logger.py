"""Shared file logger configuration for DailyChewer."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dailychewer_backend.config import Settings, load_settings


LOGGER_NAME = "dailychewer"


def get_logger(settings: Settings | None = None) -> logging.Logger:
    """Return a configured project logger writing to `data/logs/dailychewer.log`."""

    resolved_settings = settings or load_settings()
    resolved_settings.logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    level_name = os.getenv("DAILYCHEWER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    target_path = resolved_settings.log_file.resolve()
    file_handler = _find_file_handler(logger, target_path)
    if file_handler is None:
        file_handler = logging.FileHandler(target_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def _find_file_handler(logger: logging.Logger, target_path: Path) -> logging.FileHandler | None:
    """Return an existing file handler for the target log file when present."""

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if Path(handler.baseFilename).resolve() == target_path:
                    return handler
            except OSError:
                continue
    return None

