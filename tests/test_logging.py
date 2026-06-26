"""Tests for logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from shop_pipeline.logging_setup import get_logger, setup_logging


def test_get_logger_returns_named_logger():
    log = get_logger("shop_pipeline.test")
    assert log.name == "shop_pipeline.test"
    assert isinstance(log, logging.Logger)


def test_setup_logging_creates_log_file(tmp_path):
    log_path = tmp_path / "test.log"
    setup_logging(log_file=log_path, level="DEBUG")
    log = get_logger("shop_pipeline.file_test")
    log.info("hello world")
    # Flush and close file handlers so the file is fully written
    from shop_pipeline import logging_setup
    for h in logging_setup._root_handlers:
        h.flush()
        if hasattr(h, "close"):
            h.close()
    assert log_path.exists()
    assert "hello world" in log_path.read_text(encoding="utf-8")


def test_setup_logging_idempotent():
    """Calling setup_logging twice replaces handlers, doesn't accumulate."""
    from shop_pipeline import logging_setup

    log_path = Path("test_idempotent.log")
    setup_logging(log_file=log_path, level="INFO")
    handlers_first = len(logging_setup._root_handlers)  # type: ignore[attr-defined]
    setup_logging(log_file=log_path, level="INFO")
    handlers_second = len(logging_setup._root_handlers)  # type: ignore[attr-defined]
    assert handlers_first == handlers_second
    logging_setup.reset_logging()  # closes file handles
    log_path.unlink(missing_ok=True)


def test_setup_logging_adds_file_handler_on_subsequent_call(tmp_path):
    """If first call had no file, a second call with file should add the file handler."""
    from shop_pipeline import logging_setup

    log_path = tmp_path / "late.log"
    setup_logging()  # no file
    setup_logging(log_file=log_path, level="INFO")
    log = get_logger("shop_pipeline.late")
    log.info("late binding")
    for h in logging_setup._root_handlers:  # type: ignore[attr-defined]
        h.flush()
        if hasattr(h, "close"):
            h.close()
    assert log_path.exists()
    assert "late binding" in log_path.read_text(encoding="utf-8")
