"""Document classification for routing between text-PDF, scanned-PDF, and image pipelines."""

import io
from pathlib import Path

import pdfplumber

from invoiceflow.errors import ExtractionError
from invoiceflow.models import DocumentType

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MIN_TEXT_CHARS_THRESHOLD = 40


def _is_image_source(source: Path | bytes, filename: str | None = None) -> bool:
    """Determine if input is an image via filename extension or magic bytes."""
    if isinstance(source, Path) and source.suffix.lower() in IMAGE_EXTENSIONS:
        return True
    if filename and Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
        return True

    header = source[:8] if isinstance(source, bytes) else source.open("rb").read(8)
    if header.startswith(b"\xff\xd8") or header.startswith(b"\x89PNG"):
        return True

    return False


def classify_document(source: Path | bytes, filename: str | None = None) -> DocumentType:
    """Classify input document into TEXT_PDF, SCANNED_PDF, or IMAGE."""
    if _is_image_source(source, filename):
        return DocumentType.IMAGE

    try:
        file_obj = io.BytesIO(source) if isinstance(source, bytes) else source
        with pdfplumber.open(file_obj) as pdf:
            total_chars = 0
            for page in pdf.pages:
                text = page.extract_text() or ""
                total_chars += len(text.strip())
                if total_chars >= MIN_TEXT_CHARS_THRESHOLD:
                    return DocumentType.TEXT_PDF

            return DocumentType.SCANNED_PDF
    except Exception as err:
        raise ExtractionError(f"Failed to classify document: {err}") from err
