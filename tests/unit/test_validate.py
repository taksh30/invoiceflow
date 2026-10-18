"""Unit tests for invoice validation and confidence rules."""

from datetime import date
from decimal import Decimal

from invoiceflow.models import ExtractedInvoice, ProcessingStatus
from invoiceflow.validate import ValidationResult, build_and_validate, validate_invoice


def _make_sample_invoice(
    total: Decimal = Decimal("1180.00"),
    subtotal: Decimal | None = Decimal("1000.00"),
    tax_total: Decimal | None = Decimal("180.00"),
    cgst: Decimal | None = Decimal("90.00"),
    sgst: Decimal | None = Decimal("90.00"),
    igst: Decimal | None = None,
    invoice_date: date | None = date(2024, 5, 20),
    vendor_name: str = "Acme Solutions Ltd",
    invoice_number: str | None = "INV-2024-001",
    confidence: dict[str, float] | None = None,
    overall_confidence: float = 0.90,
) -> ExtractedInvoice:
    """Helper creating a sample ExtractedInvoice for testing."""
    default_conf = {
        "total": 0.90,
        "invoice_date": 0.90,
        "vendor_name": 0.90,
        "invoice_number": 0.90,
    }
    return ExtractedInvoice(
        vendor_name=vendor_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        currency="INR",
        subtotal=subtotal,
        tax_total=tax_total,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        total=total,
        confidence=confidence if confidence is not None else default_conf,
        overall_confidence=overall_confidence,
    )


def test_validate_invoice_success_with_confidence_boost() -> None:
    """Valid invoice with matching arithmetic receives +0.05 confidence boost and PROCESSED."""
    invoice = _make_sample_invoice(
        total=Decimal("1180.00"),
        subtotal=Decimal("1000.00"),
        tax_total=Decimal("180.00"),
        overall_confidence=0.85,
    )
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.PROCESSED
    assert len(result.reasons) == 0
    assert result.invoice.overall_confidence == 0.90


def test_validate_invoice_confidence_boost_capped_at_one() -> None:
    """Confidence boost cannot exceed 1.0."""
    invoice = _make_sample_invoice(overall_confidence=0.98)
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.PROCESSED
    assert result.invoice.overall_confidence == 1.0


def test_validate_invoice_arithmetic_boundary_diff_one() -> None:
    """Difference of exactly 1.00 passes arithmetic check and receives boost."""
    # 1000.00 + 180.00 = 1180.00 vs 1181.00 (diff: 1.00)
    invoice = _make_sample_invoice(total=Decimal("1181.00"), overall_confidence=0.85)
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.PROCESSED
    assert len(result.reasons) == 0
    assert result.invoice.overall_confidence == 0.90


def test_validate_invoice_arithmetic_mismatch_fails() -> None:
    """Difference of 1.01 fails arithmetic check and flags needs_review."""
    invoice = _make_sample_invoice(total=Decimal("1181.01"), overall_confidence=0.85)
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.NEEDS_REVIEW
    assert any("does not match Total" in r for r in result.reasons)
    # No confidence boost applied on mismatch
    assert result.invoice.overall_confidence == 0.85


def test_validate_invoice_gst_components_mismatch() -> None:
    """CGST + SGST mismatching tax_total flags needs_review."""
    invoice = _make_sample_invoice(
        tax_total=Decimal("180.00"),
        cgst=Decimal("100.00"),
        sgst=Decimal("100.00"),  # sum = 200.00 vs tax_total 180.00
    )
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.NEEDS_REVIEW
    assert any("GST components sum" in r for r in result.reasons)


def test_validate_invoice_low_key_field_confidence() -> None:
    """Confidence below 0.60 on key fields flags needs_review."""
    conf = {
        "total": 0.55,  # below 0.60
        "invoice_date": 0.90,
        "vendor_name": 0.90,
    }
    invoice = _make_sample_invoice(confidence=conf)
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.NEEDS_REVIEW
    assert any("total" in r and "below threshold" in r for r in result.reasons)


def test_validate_invoice_missing_invoice_date() -> None:
    """Missing invoice date flags needs_review."""
    invoice = _make_sample_invoice(invoice_date=None)
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.NEEDS_REVIEW
    assert any("Invoice date is missing" in r for r in result.reasons)


def test_validate_invoice_unknown_vendor() -> None:
    """Unknown vendor name flags needs_review."""
    invoice = _make_sample_invoice(vendor_name="Unknown Vendor")
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.NEEDS_REVIEW
    assert any("Vendor name is missing or unknown" in r for r in result.reasons)


def test_validate_invoice_without_subtotal_skips_arithmetic_check() -> None:
    """When subtotal or tax_total is missing, arithmetic cross-check is cleanly skipped."""
    invoice = _make_sample_invoice(subtotal=None, tax_total=None)
    result = validate_invoice(invoice)

    assert result.status == ProcessingStatus.PROCESSED
    assert len(result.reasons) == 0


def test_build_and_validate_helper() -> None:
    """build_and_validate convenience helper accepts kwargs and validates ExtractedInvoice."""
    result = build_and_validate(
        vendor_name="Acme Corp",
        invoice_number="INV-101",
        invoice_date=date(2024, 6, 1),
        total=Decimal("500.00"),
        confidence={"total": 0.9, "invoice_date": 0.9, "vendor_name": 0.9},
    )
    assert isinstance(result, ValidationResult)
    assert result.status == ProcessingStatus.PROCESSED
    assert result.invoice.vendor_name == "Acme Corp"


def test_validate_invoice_with_tax_total_but_no_gst_components() -> None:
    """Tax total without individual GST splits does not raise GST components mismatch."""
    invoice = _make_sample_invoice(
        total=Decimal("110.00"),
        subtotal=Decimal("100.00"),
        tax_total=Decimal("10.00"),
        cgst=None,
        sgst=None,
        igst=None,
    )
    result = validate_invoice(invoice)
    assert result.status == ProcessingStatus.PROCESSED
    assert len(result.reasons) == 0
