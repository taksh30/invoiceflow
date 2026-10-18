"""Tests for domain data models and pydantic validation."""

from datetime import date
from decimal import Decimal

import pydantic
import pytest

from invoiceflow.models import (
    DocumentSource,
    DocumentType,
    ExtractedInvoice,
    FieldResult,
    ProcessingStatus,
    RawDocument,
)


def test_document_enums() -> None:
    """Verify document enum values."""
    assert DocumentSource.FOLDER == "folder"
    assert DocumentSource.EMAIL == "email"

    assert DocumentType.TEXT_PDF == "text_pdf"
    assert DocumentType.SCANNED_PDF == "scanned_pdf"
    assert DocumentType.IMAGE == "image"

    assert ProcessingStatus.PROCESSED == "processed"
    assert ProcessingStatus.NEEDS_REVIEW == "needs_review"
    assert ProcessingStatus.DUPLICATE == "duplicate"
    assert ProcessingStatus.FAILED == "failed"


def test_raw_document() -> None:
    """Verify RawDocument instantiation and types."""
    doc = RawDocument(
        content=b"sample-pdf-bytes",
        filename="invoice_001.pdf",
        source=DocumentSource.FOLDER,
        source_ref="/invoices/invoice_001.pdf",
    )
    assert doc.filename == "invoice_001.pdf"
    assert doc.source == DocumentSource.FOLDER
    assert doc.content == b"sample-pdf-bytes"


def test_field_result() -> None:
    """Verify FieldResult confidence validation."""
    valid_res = FieldResult(value="Acme Corp", confidence=0.9, span="Acme Corp Ltd")
    assert valid_res.value == "Acme Corp"
    assert valid_res.confidence == 0.9

    with pytest.raises(pydantic.ValidationError):
        FieldResult(value="Acme", confidence=1.5)

    with pytest.raises(pydantic.ValidationError):
        FieldResult(value="Acme", confidence=-0.1)


def test_extracted_invoice_valid() -> None:
    """Verify valid ExtractedInvoice creation."""
    inv = ExtractedInvoice(
        vendor_name="Acme Corp",
        vendor_tax_id="29ABCDE1234F1Z5",
        invoice_number="INV-2024-001",
        invoice_date=date(2024, 5, 1),
        currency="INR",
        subtotal=Decimal("1000.00"),
        tax_total=Decimal("180.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        total=Decimal("1180.00"),
        confidence={"total": 0.95, "vendor_name": 0.90},
        overall_confidence=0.92,
    )
    assert inv.vendor_name == "Acme Corp"
    assert inv.total == Decimal("1180.00")
    assert inv.currency == "INR"


def test_extracted_invoice_currency_validation() -> None:
    """Verify currency must be 3 uppercase alphabetical characters."""
    with pytest.raises(pydantic.ValidationError, match="ISO"):
        ExtractedInvoice(vendor_name="Acme", total=Decimal("100.00"), currency="US")

    with pytest.raises(pydantic.ValidationError, match="ISO"):
        ExtractedInvoice(vendor_name="Acme", total=Decimal("100.00"), currency="inr")


def test_extracted_invoice_total_positive() -> None:
    """Verify total must be greater than zero."""
    with pytest.raises(pydantic.ValidationError, match="greater than 0"):
        ExtractedInvoice(vendor_name="Acme", total=Decimal("0.00"))

    with pytest.raises(pydantic.ValidationError, match="greater than 0"):
        ExtractedInvoice(vendor_name="Acme", total=Decimal("-50.00"))


def test_extracted_invoice_date_sanity() -> None:
    """Verify invoice_date sanity check (not before 2000, not in future)."""
    with pytest.raises(pydantic.ValidationError, match="year 2000"):
        ExtractedInvoice(
            vendor_name="Acme",
            total=Decimal("100.00"),
            invoice_date=date(1995, 1, 1),
        )

    with pytest.raises(pydantic.ValidationError, match="future"):
        ExtractedInvoice(
            vendor_name="Acme",
            total=Decimal("100.00"),
            invoice_date=date(date.today().year + 2, 1, 1),
        )


def test_extracted_invoice_money_scale() -> None:
    """Verify Decimal amounts reject more than 2 decimal places."""
    with pytest.raises(pydantic.ValidationError, match="decimal places"):
        ExtractedInvoice(vendor_name="Acme", total=Decimal("100.123"))

    with pytest.raises(pydantic.ValidationError, match="decimal places"):
        ExtractedInvoice(
            vendor_name="Acme",
            total=Decimal("100.00"),
            subtotal=Decimal("50.1234"),
        )
