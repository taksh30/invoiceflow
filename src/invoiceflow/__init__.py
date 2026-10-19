"""InvoiceFlow: Invoice and receipt auto-processor package."""

from invoiceflow.dedupe import (
    DeduplicationResult,
    find_duplicate,
    normalize_vendor,
    vendor_similarity,
)
from invoiceflow.export import GoogleSheetsExporter, export_monthly_data
from invoiceflow.extract.llm import (
    FakeLLMClient,
    LLMClient,
    LLMExtractor,
    LLMResponse,
)
from invoiceflow.pipeline import Pipeline, PipelineResult
from invoiceflow.sources.email_imap import ImapEmailSource
from invoiceflow.validate import ValidationResult, build_and_validate, validate_invoice

__version__ = "0.1.0"
__all__ = [
    "DeduplicationResult",
    "FakeLLMClient",
    "GoogleSheetsExporter",
    "ImapEmailSource",
    "LLMClient",
    "LLMExtractor",
    "LLMResponse",
    "Pipeline",
    "PipelineResult",
    "ValidationResult",
    "build_and_validate",
    "export_monthly_data",
    "find_duplicate",
    "normalize_vendor",
    "validate_invoice",
    "vendor_similarity",
]
