"""InvoiceFlow: Invoice and receipt auto-processor package."""

from invoiceflow.dedupe import (
    DeduplicationResult,
    find_duplicate,
    normalize_vendor,
    vendor_similarity,
)
from invoiceflow.validate import ValidationResult, build_and_validate, validate_invoice

__version__ = "0.1.0"
__all__ = [
    "DeduplicationResult",
    "ValidationResult",
    "build_and_validate",
    "find_duplicate",
    "normalize_vendor",
    "validate_invoice",
    "vendor_similarity",
]
