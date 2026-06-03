"""structlog + stdlib logging configuration with rotating file output.

Emits JSON log lines with ``timestamp, level, event, user_id, ip, request_id,
detail`` fields. Never logs secrets — callers must pass only the last 8 chars of
any token (see :func:`backend.security.token_tail`).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

_CONFIGURED = False


def configure_logging(log_level: str, log_file: str) -> None:
    """Configure structlog to emit JSON to a rotating file and to stderr.

    Args:
        log_level: Level name (e.g. ``"INFO"``).
        log_file: Destination path; parent dirs are created.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, log_level.upper(), logging.INFO)
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 50MB per file, keep 5 backups.
    file_handler = RotatingFileHandler(
        str(path), maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    stream_handler = logging.StreamHandler()

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    for handler in (file_handler, stream_handler):
        handler.setLevel(level)
        root.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str = "backend"):
    """Return a structlog logger bound with the given ``name``."""
    return structlog.get_logger(name)
