"""Logging setup.

Single point to configure logging. Idempotent: safe to call multiple times.
For tests, call reset_logging() to start fresh.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

# Track handlers so setup is idempotent
_root_handlers: list[logging.Handler] = []


def setup_logging(
    log_file: Path | None = None,
    level: str = "INFO",
    fmt: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
) -> None:
    """Configure root logger. Safe to call multiple times; replaces existing config."""
    reset_logging()
    root = logging.getLogger()
    root.setLevel(level.upper())

    formatter = logging.Formatter(fmt)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)
    _root_handlers.append(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        _root_handlers.append(file_handler)


def reset_logging() -> None:
    """Remove all handlers we attached. For tests."""
    root = logging.getLogger()
    for h in _root_handlers:
        with contextlib.suppress(Exception):
            h.close()
        if h in root.handlers:
            root.removeHandler(h)
    _root_handlers.clear()


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Configures logging on first use."""
    if not _root_handlers:
        setup_logging()
    return logging.getLogger(name)
