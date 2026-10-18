"""InvoiceFlow: Invoice and receipt auto-processor package."""

from invoiceflow.validate import ValidationResult, build_and_validate, validate_invoice

__version__ = "0.1.0"
__all__ = ["ValidationResult", "build_and_validate", "validate_invoice"]
