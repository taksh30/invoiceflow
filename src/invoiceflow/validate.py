"""Validation engine and confidence cross-checks for extracted invoice data."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from invoiceflow.models import ExtractedInvoice, ProcessingStatus

ARITHMETIC_TOLERANCE = Decimal("1.00")
DEFAULT_KEY_FIELDS = ("total", "invoice_date", "vendor_name")
MIN_CONFIDENCE_THRESHOLD = 0.60


class ValidationResult(BaseModel):
    """Container for post-validation invoice data and processing lifecycle status."""

    invoice: ExtractedInvoice
    status: ProcessingStatus
    reasons: list[str] = Field(default_factory=list)


def _check_arithmetic(invoice: ExtractedInvoice) -> tuple[bool, str | None, bool]:
    """Validate subtotal + tax_total against total with tolerance.

    Returns (is_valid, error_reason, should_boost).
    """
    if invoice.subtotal is None or invoice.tax_total is None:
        return True, None, False

    expected_total = invoice.subtotal + invoice.tax_total
    diff = abs(expected_total - invoice.total)

    if diff <= ARITHMETIC_TOLERANCE:
        return True, None, True

    reason = (
        f"Subtotal ({invoice.subtotal}) + Tax ({invoice.tax_total}) = {expected_total} "
        f"does not match Total ({invoice.total}), diff: {diff}"
    )
    return False, reason, False


def _check_gst_components(invoice: ExtractedInvoice) -> str | None:
    """Validate that CGST, SGST, and IGST components sum to tax_total when present."""
    if invoice.tax_total is None:
        return None

    components = [c for c in (invoice.cgst, invoice.sgst, invoice.igst) if c is not None]
    if not components:
        return None

    comp_sum = sum(components, Decimal("0.00"))
    diff = abs(comp_sum - invoice.tax_total)

    if diff > ARITHMETIC_TOLERANCE:
        return (
            f"GST components sum ({comp_sum}) does not match Tax total "
            f"({invoice.tax_total}), diff: {diff}"
        )
    return None


def _check_key_fields(
    invoice: ExtractedInvoice,
    key_fields: tuple[str, ...],
    min_confidence: float,
) -> list[str]:
    """Verify that all key fields are present and meet minimum confidence threshold."""
    reasons: list[str] = []

    for field_name in key_fields:
        if field_name == "vendor_name":
            if not invoice.vendor_name or invoice.vendor_name.strip() in ("", "Unknown Vendor"):
                reasons.append("Vendor name is missing or unknown")
                continue
        elif field_name == "invoice_date":
            if invoice.invoice_date is None:
                reasons.append("Invoice date is missing")
                continue
        elif field_name == "total":
            pass

        conf = invoice.confidence.get(field_name)
        if conf is None or conf < min_confidence:
            conf_val = 0.0 if conf is None else conf
            reasons.append(
                f"Key field '{field_name}' confidence ({conf_val:.2f}) "
                f"is below threshold {min_confidence:.2f}"
            )

    return reasons


def validate_invoice(
    invoice: ExtractedInvoice,
    key_fields: tuple[str, ...] = DEFAULT_KEY_FIELDS,
    min_confidence: float = MIN_CONFIDENCE_THRESHOLD,
) -> ValidationResult:
    """Run cross-validation and confidence threshold rules on an ExtractedInvoice."""
    reasons: list[str] = []

    # 1. Arithmetic cross-checks
    arith_valid, arith_reason, should_boost = _check_arithmetic(invoice)
    if not arith_valid and arith_reason:
        reasons.append(arith_reason)

    # 2. GST breakdown cross-checks
    gst_reason = _check_gst_components(invoice)
    if gst_reason:
        reasons.append(gst_reason)

    # 3. Key field presence and confidence thresholds
    field_reasons = _check_key_fields(invoice, key_fields, min_confidence)
    reasons.extend(field_reasons)

    # 4. Confidence boost if cross-check passes
    updated_confidence = invoice.overall_confidence
    if should_boost and not reasons:
        updated_confidence = min(1.0, round(invoice.overall_confidence + 0.05, 3))

    final_invoice = invoice.model_copy(update={"overall_confidence": updated_confidence})
    status = ProcessingStatus.NEEDS_REVIEW if reasons else ProcessingStatus.PROCESSED

    return ValidationResult(invoice=final_invoice, status=status, reasons=reasons)


def build_and_validate(**kwargs: Any) -> ValidationResult:
    """Construct an ExtractedInvoice and run validation."""
    invoice = ExtractedInvoice(**kwargs)
    return validate_invoice(invoice)
