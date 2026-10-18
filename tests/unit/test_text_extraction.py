"""Unit tests for text extraction via pdfplumber and OCR."""

import shutil
from pathlib import Path

import pytest
from PIL import Image

from invoiceflow.extract.text import (
    extract_from_image,
    extract_from_scanned_pdf,
    extract_from_text_pdf,
    extract_text,
    preprocess_image,
)
from invoiceflow.models import DocumentType

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
HAS_TESSERACT = bool(shutil.which("tesseract"))


def test_preprocess_image() -> None:
    """Verify image preprocessing converts to grayscale and binarizes."""
    img = Image.new("RGB", (100, 100), color=(200, 200, 200))
    processed = preprocess_image(img)
    assert processed.mode == "L"
    assert processed.size == (100, 100)


def test_extract_from_text_pdf() -> None:
    """Verify digital text PDF extraction extracts text and coordinates via pdfplumber."""
    pdf_path = FIXTURES_DIR / "sample_text.pdf"
    result = extract_from_text_pdf(pdf_path)

    assert result.method == "pdfplumber"
    assert len(result.pages) == 1
    assert "INVOICE #INV-2024-001" in result.raw_text
    assert "Acme Corporation" in result.raw_text
    assert "Total: 1500.00" in result.raw_text

    # Verify bounding boxes
    assert len(result.words) > 0
    first_word = result.words[0]
    assert first_word.text == "INVOICE"
    assert first_word.x0 < first_word.x1
    assert first_word.top < first_word.bottom
    assert first_word.page_number == 1


@pytest.mark.ocr
@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract OCR binary not installed")
def test_extract_from_image_ocr() -> None:
    """Verify image extraction runs preprocessing and OCR on receipt image."""
    img_path = FIXTURES_DIR / "sample_receipt.png"
    result = extract_from_image(img_path)

    assert result.method == "tesseract_ocr"
    assert len(result.pages) == 1
    assert any(term in result.raw_text for term in ["RETAIL", "Receipt", "Total", "236.00"])
    assert len(result.words) > 0
    assert result.words[0].page_number == 1


@pytest.mark.ocr
@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract OCR binary not installed")
def test_extract_from_scanned_pdf_ocr() -> None:
    """Verify scanned PDF renders pages and extracts text via OCR."""
    scanned_path = FIXTURES_DIR / "sample_scanned.pdf"
    result = extract_from_scanned_pdf(scanned_path)

    assert result.method == "tesseract_ocr"
    assert len(result.pages) == 1
    assert any(term in result.raw_text for term in ["RETAIL", "Receipt", "Total", "236.00"])
    assert len(result.words) > 0


def test_extract_text_dispatcher() -> None:
    """Verify extract_text auto-classifies and dispatches appropriately."""
    pdf_path = FIXTURES_DIR / "sample_text.pdf"
    res = extract_text(pdf_path, doc_type=DocumentType.TEXT_PDF)
    assert res.method == "pdfplumber"
    assert "INVOICE" in res.raw_text
