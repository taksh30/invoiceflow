"""Unit tests for document classification into text-PDF, scanned-PDF, or image."""

from pathlib import Path

import pytest

from invoiceflow.errors import ExtractionError
from invoiceflow.extract.classify import classify_document
from invoiceflow.models import DocumentType

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_classify_text_pdf() -> None:
    """Verify digital text PDF is classified as TEXT_PDF."""
    path = FIXTURES_DIR / "sample_text.pdf"
    assert classify_document(path) == DocumentType.TEXT_PDF
    assert classify_document(path.read_bytes(), filename="sample_text.pdf") == DocumentType.TEXT_PDF


def test_classify_scanned_pdf() -> None:
    """Verify raster image PDF lacking digital text is classified as SCANNED_PDF."""
    path = FIXTURES_DIR / "sample_scanned.pdf"
    assert classify_document(path) == DocumentType.SCANNED_PDF
    assert (
        classify_document(path.read_bytes(), filename="sample_scanned.pdf")
        == DocumentType.SCANNED_PDF
    )


def test_classify_image() -> None:
    """Verify image files are classified as IMAGE by extension and magic bytes."""
    path = FIXTURES_DIR / "sample_receipt.png"
    assert classify_document(path) == DocumentType.IMAGE
    assert classify_document(path.read_bytes()) == DocumentType.IMAGE


def test_classify_corrupted_data(tmp_path: Path) -> None:
    """Verify corrupted non-image, non-PDF data raises ExtractionError."""
    corrupted = tmp_path / "corrupted.pdf"
    corrupted.write_bytes(b"invalid corrupt binary data")
    with pytest.raises(ExtractionError, match="Failed to classify"):
        classify_document(corrupted)
