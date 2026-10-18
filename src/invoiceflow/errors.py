"""Domain exception hierarchy for InvoiceFlow."""


class InvoiceFlowError(Exception):
    """Base domain exception for all InvoiceFlow errors."""


class IngestError(InvoiceFlowError):
    """Raised when document ingestion or file reading fails."""


class ExtractionError(InvoiceFlowError):
    """Raised when document parsing, OCR, or field extraction fails."""


class ValidationError(InvoiceFlowError):
    """Raised when extracted data fails validation or cross-checks."""
