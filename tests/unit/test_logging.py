"""Tests for logging configuration and contextual adapters."""

import json
import logging

import pytest

from invoiceflow.utils.logging import JSONFormatter, get_logger, setup_logging


def test_setup_logging_text(caplog: pytest.LogCaptureFixture) -> None:
    """Verify standard text logging setup."""
    setup_logging(level="DEBUG", json_format=False)
    logger = get_logger("test_text")

    with caplog.at_level(logging.DEBUG):
        logger.debug("Debug message")

    assert "Debug message" in caplog.text


def test_json_formatter() -> None:
    """Verify JSONFormatter outputs valid JSON with contextual metadata."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_json",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Structured event",
        args=(),
        exc_info=None,
    )
    record.document_id = 42  # type: ignore[attr-defined]
    record.stage = "ocr"  # type: ignore[attr-defined]

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["name"] == "test_json"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Structured event"
    assert parsed["document_id"] == 42
    assert parsed["stage"] == "ocr"


def test_get_logger_context() -> None:
    """Verify get_logger binds extra contextual metadata."""
    adapter = get_logger("test_adapter", document_id=99, stage="validation")
    assert adapter.extra == {"document_id": 99, "stage": "validation"}
