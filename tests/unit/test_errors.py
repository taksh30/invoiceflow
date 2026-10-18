"""Tests for domain error hierarchy."""

import pytest

from invoiceflow.errors import (
    ExtractionError,
    IngestError,
    InvoiceFlowError,
    ValidationError,
)


def test_exception_hierarchy() -> None:
    """Verify all domain errors inherit from InvoiceFlowError."""
    assert issubclass(IngestError, InvoiceFlowError)
    assert issubclass(ExtractionError, InvoiceFlowError)
    assert issubclass(ValidationError, InvoiceFlowError)
    assert issubclass(InvoiceFlowError, Exception)


def test_raise_and_catch_domain_error() -> None:
    """Verify catching domain errors by base class."""
    with pytest.raises(InvoiceFlowError) as exc_info:
        raise IngestError("Failed to read file")

    assert "Failed to read file" in str(exc_info.value)
