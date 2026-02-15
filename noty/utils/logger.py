"""Централизованная конфигурация логирования."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def _resolve_log_level(level: int | str | None) -> int:
    if isinstance(level, int):
        return level

    if isinstance(level, str):
        resolved = logging.getLevelName(level.upper())
        if isinstance(resolved, int):
            return resolved

    env_level = os.getenv("NOTY_LOG_LEVEL", "INFO").upper()
    env_resolved = logging.getLevelName(env_level)
    if isinstance(env_resolved, int):
        return env_resolved

    return logging.INFO


def configure_logging(level: int | str | None = None, log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(stream=sys.stdout)]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=_resolve_log_level(level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
