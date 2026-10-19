"""Unit tests for structured JSON logging and contextual adapters."""

import json
import logging
from typing import Any

from invoiceflow.utils.logging import ContextAdapter, JSONFormatter, get_logger, setup_logging


def test_json_formatter_standard_fields() -> None:
    """Verify that JSONFormatter produces valid JSON with core fields."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Processing file %s",
        args=("inv123.pdf",),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["name"] == "test.logger"
    assert parsed["message"] == "Processing file inv123.pdf"
    assert "timestamp" in parsed
    assert "pathname" not in parsed
    assert "lineno" not in parsed


def test_json_formatter_extra_fields() -> None:
    """Verify that JSONFormatter captures custom extra attributes dynamically."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname="test.py",
        lineno=25,
        msg="Validation warning",
        args=(),
        exc_info=None,
    )
    record.document_id = 42  # type: ignore[attr-defined]
    record.stage = "validation"  # type: ignore[attr-defined]
    record.vendor = "Acme Corp"  # type: ignore[attr-defined]
    record.retry_count = 3  # type: ignore[attr-defined]

    output = formatter.format(record)
    parsed: dict[str, Any] = json.loads(output)

    assert parsed["document_id"] == 42
    assert parsed["stage"] == "validation"
    assert parsed["vendor"] == "Acme Corp"
    assert parsed["retry_count"] == 3


def test_json_formatter_exception() -> None:
    """Verify that exceptions are formatted as strings in the JSON payload."""
    formatter = JSONFormatter()
    try:
        raise ValueError("Simulated parse failure")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=50,
        msg="Error encountered",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "ERROR"
    assert "exception" in parsed
    assert "Simulated parse failure" in parsed["exception"]


def test_context_adapter_and_get_logger() -> None:
    """Verify that get_logger returns a ContextAdapter injecting context."""
    adapter = get_logger("pipeline.test", document_id=101, stage="ingest", source="email")
    assert isinstance(adapter, ContextAdapter)
    msg, kwargs = adapter.process("Sample message", {})

    assert msg == "Sample message"
    assert "extra" in kwargs
    assert kwargs["extra"]["document_id"] == 101
    assert kwargs["extra"]["stage"] == "ingest"
    assert kwargs["extra"]["source"] == "email"


def test_setup_logging_text_and_json() -> None:
    """Verify setup_logging configures appropriate formatters."""
    setup_logging(level="DEBUG", json_format=False)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    handlers = [h for h in root.handlers if h.__class__.__name__ != "LogCaptureHandler"]
    assert handlers
    assert not isinstance(handlers[0].formatter, JSONFormatter)

    setup_logging(level="INFO", json_format=True)
    assert root.level == logging.INFO
    handlers = [h for h in root.handlers if h.__class__.__name__ != "LogCaptureHandler"]
    assert handlers
    assert isinstance(handlers[0].formatter, JSONFormatter)
