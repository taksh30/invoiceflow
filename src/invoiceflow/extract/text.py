"""Text extraction engine utilizing pdfplumber for digital PDFs and OCR for scanned documents."""

import io
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import pypdfium2
import pytesseract
from PIL import Image

from invoiceflow.extract.classify import classify_document
from invoiceflow.models import DocumentType


@dataclass(frozen=True)
class WordBox:
    """Individual word bounding box and location metadata."""

    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    page_number: int


@dataclass(frozen=True)
class TextResult:
    """Aggregated output of text extraction with page text and bounding boxes."""

    raw_text: str
    pages: list[str]
    words: list[WordBox]
    method: str


def preprocess_image(image: Image.Image) -> Image.Image:
    """Preprocess image for OCR: convert to grayscale and binarize."""
    gray = image.convert("L")
    threshold = 150
    table = [0 if i < threshold else 255 for i in range(256)]
    binarized = gray.point(table, mode="1")
    return binarized.convert("L")


def extract_from_text_pdf(source: Path | bytes) -> TextResult:
    """Extract digital text and word bounding boxes using pdfplumber."""
    file_obj = io.BytesIO(source) if isinstance(source, bytes) else source
    pages: list[str] = []
    words: list[WordBox] = []

    with pdfplumber.open(file_obj) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            pages.append(page_text)
            for w in page.extract_words():
                words.append(
                    WordBox(
                        text=str(w["text"]),
                        x0=float(w["x0"]),
                        top=float(w["top"]),
                        x1=float(w["x1"]),
                        bottom=float(w["bottom"]),
                        page_number=page_idx,
                    )
                )

    full_text = "\n\n".join(pages).strip()
    return TextResult(raw_text=full_text, pages=pages, words=words, method="pdfplumber")


def extract_from_image(source: Path | bytes | Image.Image, page_number: int = 1) -> TextResult:
    """Preprocess image and perform OCR with word-level bounding boxes."""
    if isinstance(source, Image.Image):
        img = source
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source))
    else:
        img = Image.open(source)

    processed = preprocess_image(img)
    data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)

    words: list[WordBox] = []
    page_tokens: list[str] = []

    for i in range(len(data["text"])):
        token = data["text"][i].strip()
        if not token:
            continue
        page_tokens.append(token)
        x = float(data["left"][i])
        y = float(data["top"][i])
        w = float(data["width"][i])
        h = float(data["height"][i])
        words.append(
            WordBox(
                text=token,
                x0=x,
                top=y,
                x1=x + w,
                bottom=y + h,
                page_number=page_number,
            )
        )

    raw_text = pytesseract.image_to_string(processed).strip()
    return TextResult(
        raw_text=raw_text,
        pages=[raw_text],
        words=words,
        method="tesseract_ocr",
    )


def extract_from_scanned_pdf(source: Path | bytes) -> TextResult:
    """Render PDF pages to PIL images via pypdfium2 and extract text via OCR."""
    file_bytes = source if isinstance(source, bytes) else source.read_bytes()
    pdf = pypdfium2.PdfDocument(file_bytes)

    pages: list[str] = []
    words: list[WordBox] = []

    for page_idx in range(len(pdf)):
        page = pdf[page_idx]
        pil_img = page.render(scale=2.0).to_pil()
        res = extract_from_image(pil_img, page_number=page_idx + 1)
        pages.append(res.raw_text)
        words.extend(res.words)

    full_text = "\n\n".join(pages).strip()
    return TextResult(raw_text=full_text, pages=pages, words=words, method="tesseract_ocr")


def extract_text(source: Path | bytes, doc_type: DocumentType | None = None) -> TextResult:
    """Unified entry point extracting text based on document classification."""
    if doc_type is None:
        doc_type = classify_document(source)

    if doc_type == DocumentType.TEXT_PDF:
        return extract_from_text_pdf(source)
    if doc_type == DocumentType.SCANNED_PDF:
        return extract_from_scanned_pdf(source)
    return extract_from_image(source)
