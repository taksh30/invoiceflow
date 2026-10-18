"""Pydantic domain models and data schemas for InvoiceFlow."""

import re
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DocumentSource(StrEnum):
    """Source origin of an ingested document."""

    FOLDER = "folder"
    EMAIL = "email"


class DocumentType(StrEnum):
    """Classified document file type."""

    TEXT_PDF = "text_pdf"
    SCANNED_PDF = "scanned_pdf"
    IMAGE = "image"


class ProcessingStatus(StrEnum):
    """Processing lifecycle status of a document."""

    PROCESSED = "processed"
    NEEDS_REVIEW = "needs_review"
    DUPLICATE = "duplicate"
    FAILED = "failed"


class RawDocument(BaseModel):
    """Container for raw unparsed document payload and origin metadata."""

    content: bytes
    filename: str
    source: DocumentSource
    source_ref: str


class FieldResult(BaseModel):
    """Result of an individual field extraction with confidence and source span."""

    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    span: str | None = None


class ExtractedInvoice(BaseModel):
    """Validated structured invoice data with field-level confidences."""

    vendor_name: str
    vendor_tax_id: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str = Field(default="INR")

    subtotal: Decimal | None = None
    tax_total: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    total: Decimal

    confidence: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 1.0
    duplicate_of: int | None = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, val: str) -> str:
        """Validate 3-letter ISO uppercase currency code."""
        if not re.match(r"^[A-Z]{3}$", val):
            raise ValueError(f"Currency must be 3-letter uppercase ISO code: {val!r}")
        return val

    @field_validator("total", "subtotal", "tax_total", "cgst", "sgst", "igst")
    @classmethod
    def validate_money_scale(cls, val: Decimal | None) -> Decimal | None:
        """Enforce maximum of 2 decimal places for monetary fields."""
        if val is None:
            return None
        exponent = val.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError(f"Monetary value cannot have more than 2 decimal places: {val}")
        return val

    @field_validator("total")
    @classmethod
    def validate_total_positive(cls, val: Decimal) -> Decimal:
        """Enforce positive grand total."""
        if val <= Decimal("0.00"):
            raise ValueError("total must be greater than 0")
        return val

    @field_validator("invoice_date")
    @classmethod
    def validate_invoice_date(cls, val: date | None) -> date | None:
        """Validate date sanity (not before 2000, not in future)."""
        if val is None:
            return None
        if val.year < 2000:
            raise ValueError(f"Date {val} cannot be before year 2000")
        if val > date.today():
            raise ValueError(f"Date {val} cannot be in the future")
        return val
