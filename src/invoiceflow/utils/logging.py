"""Structured logging utilities with contextual metadata support."""

import json
import logging
import sys
from collections.abc import MutableMapping
from typing import Any

_STANDARD_LOG_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record into a JSON string with extra metadata."""
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if (
                key not in _STANDARD_LOG_RECORD_ATTRS
                and not key.startswith("_")
                and value is not None
            ):
                log_data[key] = value
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, default=str)


class ContextAdapter(logging.LoggerAdapter[logging.Logger]):
    """Logger adapter injecting document_id and pipeline stage metadata."""

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        """Inject extra contextual dictionary items into kwargs."""
        extra = kwargs.setdefault("extra", {})
        if self.extra:
            extra.update(self.extra)
        return msg, kwargs


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure root logging handlers and formatters."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    for handler in list(root_logger.handlers):
        if handler.__class__.__name__ == "LogCaptureHandler":
            continue
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(numeric_level)

    if json_format:
        formatter: logging.Formatter = JSONFormatter()
    else:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        formatter = logging.Formatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")

    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)


def get_logger(
    name: str,
    document_id: int | None = None,
    stage: str | None = None,
    **kwargs: Any,
) -> ContextAdapter:
    """Return a ContextAdapter for named logger with contextual metadata."""
    base_logger = logging.getLogger(name)
    extra_context: dict[str, Any] = dict(kwargs)
    if document_id is not None:
        extra_context["document_id"] = document_id
    if stage is not None:
        extra_context["stage"] = stage
    return ContextAdapter(base_logger, extra_context)
