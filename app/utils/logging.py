"""Shared rich-backed logger with optional file output."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from rich.logging import RichHandler

from app.utils.config import get_settings

_CONFIGURED = False


def get_logger(name: str = "cre_agent") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        settings = get_settings()
        handlers: list[logging.Handler] = [
            RichHandler(rich_tracebacks=True, show_path=False),
        ]
        try:
            log_path = settings.log_file_path
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            handlers.append(fh)
        except OSError:
            pass

        logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=handlers)
        _CONFIGURED = True
    return logging.getLogger(name)
