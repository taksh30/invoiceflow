"""Duplicate invoice detection using exact keys and fuzzy vendor similarity."""

import re

from pydantic import BaseModel
from rapidfuzz import fuzz

from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.db.tables import InvoiceRow
from invoiceflow.models import ExtractedInvoice, ProcessingStatus

DEFAULT_VENDOR_THRESHOLD = 90.0

LEGAL_SUFFIXES_PATTERN = re.compile(
    r"\b(?:ltd|limited|pvt|private|inc|incorporated|llc|corp|corporation|co|company)\b",
    re.IGNORECASE,
)


class DeduplicationResult(BaseModel):
    """Result of duplicate check with duplicate link and target processing status."""

    is_duplicate: bool
    duplicate_of_id: int | None = None
    status: ProcessingStatus = ProcessingStatus.PROCESSED
    reason: str | None = None


def normalize_vendor(name: str) -> str:
    """Normalize vendor name by stripping punctuation, extra spaces, and legal suffixes."""
    cleaned = re.sub(r"[^\w\s]", " ", name)
    cleaned = LEGAL_SUFFIXES_PATTERN.sub(" ", cleaned)
    return " ".join(cleaned.lower().split())


def normalize_number(num: str | None) -> str:
    """Normalize invoice identifier by stripping spaces and common separators."""
    if not num:
        return ""
    return re.sub(r"[\s\-_/#:.]", "", num).lower()


def vendor_similarity(v1: str, v2: str) -> float:
    """Compute fuzzy similarity ratio between two vendor names in range [0.0, 100.0]."""
    norm1 = normalize_vendor(v1)
    norm2 = normalize_vendor(v2)
    if not norm1 or not norm2:
        return 0.0
    return float(fuzz.token_sort_ratio(norm1, norm2))


def _is_duplicate_candidate(
    invoice: ExtractedInvoice,
    candidate: InvoiceRow,
    vendor_sim: float,
    vendor_threshold: float,
) -> bool:
    """Determine if a candidate row represents a duplicate invoice."""
    if vendor_sim < vendor_threshold:
        return False

    if invoice.total != candidate.total:
        return False

    inv_num_clean = normalize_number(invoice.invoice_number)
    cand_num_clean = normalize_number(candidate.invoice_number)

    if inv_num_clean and cand_num_clean:
        return inv_num_clean == cand_num_clean

    # When invoice numbers are missing, require date to match as well
    return invoice.invoice_date is not None and invoice.invoice_date == candidate.invoice_date


def find_duplicate(
    invoice: ExtractedInvoice,
    repo: InvoiceRepository,
    vendor_threshold: float = DEFAULT_VENDOR_THRESHOLD,
) -> DeduplicationResult:
    """Check database for duplicate invoices using exact keys and fuzzy vendor similarity."""
    candidates = repo.find_candidates(
        vendor_name=invoice.vendor_name,
        invoice_number=invoice.invoice_number,
        total=invoice.total,
        invoice_date=invoice.invoice_date,
    )

    for cand in candidates:
        sim = vendor_similarity(invoice.vendor_name, cand.vendor_name)
        if _is_duplicate_candidate(invoice, cand, sim, vendor_threshold):
            reason = (
                f"Fuzzy duplicate of invoice #{cand.id} (vendor: '{cand.vendor_name}', "
                f"similarity: {sim:.1f}%, number: '{cand.invoice_number}', total: {cand.total})"
            )
            return DeduplicationResult(
                is_duplicate=True,
                duplicate_of_id=cand.id,
                status=ProcessingStatus.DUPLICATE,
                reason=reason,
            )

    return DeduplicationResult(
        is_duplicate=False,
        duplicate_of_id=None,
        status=ProcessingStatus.PROCESSED,
        reason=None,
    )
