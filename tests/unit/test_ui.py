"""Unit and integration tests for the FastAPI + HTMX review station web application."""

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from invoiceflow.config import Settings
from invoiceflow.db.base import Base
from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.models import DocumentSource, DocumentType, ExtractedInvoice, ProcessingStatus
from invoiceflow.ui.app import create_ui_app
from invoiceflow.ui.corrections import load_corrections


@pytest.fixture
def ui_test_env(tmp_path: Path) -> tuple[TestClient, Session, Settings]:
    """Configure isolated in-memory DB and test client for UI tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    corrections_dir = tmp_path / "corrections"
    corrections_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        raw_dir=raw_dir,
        corrections_dir=corrections_dir,
        database_url="sqlite:///:memory:",
    )

    app = create_ui_app(settings=settings, engine=engine)
    client = TestClient(app)

    return client, session, settings


def test_review_queue_empty(ui_test_env: tuple[TestClient, Session, Settings]) -> None:
    """Verify empty review queue displays celebration message."""
    client, _, _ = ui_test_env
    res = client.get("/")
    assert res.status_code == 200
    assert "Human Review Queue" in res.text
    assert "No invoices currently require review" in res.text


def test_review_queue_lists_needs_review_only(
    ui_test_env: tuple[TestClient, Session, Settings],
    tmp_path: Path,
) -> None:
    """Verify queue displays needs_review documents and ignores processed ones."""
    client, session, _ = ui_test_env
    repo = InvoiceRepository(session)

    # 1. Document needing review
    doc1 = repo.add_document(
        file_sha256="hash111",
        original_name="low_conf.pdf",
        stored_path=str(tmp_path / "low_conf.pdf"),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.NEEDS_REVIEW.value,
        error="Confidence 0.45 < 0.60 threshold",
    )
    repo.add_invoice(
        doc1.id,
        ExtractedInvoice(
            vendor_name="Unclear Vendor",
            currency="INR",
            total=Decimal("150.00"),
            overall_confidence=0.45,
        ),
    )

    # 2. Document already processed
    repo.add_document(
        file_sha256="hash222",
        original_name="processed.pdf",
        stored_path=str(tmp_path / "processed.pdf"),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.PROCESSED.value,
    )
    session.commit()

    res = client.get("/")
    assert res.status_code == 200
    assert "low_conf.pdf" in res.text
    assert "Unclear Vendor" in res.text
    assert "processed.pdf" not in res.text


def test_review_document_detail_view(
    ui_test_env: tuple[TestClient, Session, Settings],
    tmp_path: Path,
) -> None:
    """Verify review detail page renders split view and document link."""
    client, session, _ = ui_test_env
    repo = InvoiceRepository(session)

    doc_file = tmp_path / "invoice_review.pdf"
    doc_file.write_bytes(b"%PDF-1.4 test")

    doc = repo.add_document(
        file_sha256="hash333",
        original_name="invoice_review.pdf",
        stored_path=str(doc_file),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.NEEDS_REVIEW.value,
        error="Arithmetic discrepancy",
    )
    repo.add_invoice(
        doc.id,
        ExtractedInvoice(
            vendor_name="Glitchy Goods",
            currency="INR",
            total=Decimal("800.00"),
            subtotal=Decimal("700.00"),
            tax_total=Decimal("50.00"),
            overall_confidence=0.55,
        ),
    )
    session.commit()

    res = client.get(f"/review/{doc.id}")
    assert res.status_code == 200
    assert "invoice_review.pdf" in res.text
    assert "Glitchy Goods" in res.text
    assert f"/document/{doc.id}/file" in res.text
    assert "Arithmetic discrepancy" in res.text

    # Non-existent doc
    res_404 = client.get("/review/99999")
    assert res_404.status_code == 404


def test_stream_document_file(
    ui_test_env: tuple[TestClient, Session, Settings],
    tmp_path: Path,
) -> None:
    """Verify streaming raw document file with correct media type."""
    client, session, _ = ui_test_env
    repo = InvoiceRepository(session)

    pdf_file = tmp_path / "raw_invoice.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 sample content")

    doc = repo.add_document(
        file_sha256="hash_stream",
        original_name="raw_invoice.pdf",
        stored_path=str(pdf_file),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.NEEDS_REVIEW.value,
    )
    session.commit()

    res = client.get(f"/document/{doc.id}/file")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content == b"%PDF-1.4 sample content"


def test_save_correction_promotes_and_stores_training_example(
    ui_test_env: tuple[TestClient, Session, Settings],
    tmp_path: Path,
) -> None:
    """Verify submitting correction updates DB, status, and saves training example."""
    client, session, settings = ui_test_env
    repo = InvoiceRepository(session)

    pdf_file = tmp_path / "corrigible.pdf"
    pdf_file.write_bytes(b"%PDF-1.4")

    doc = repo.add_document(
        file_sha256="hash_corrigible",
        original_name="corrigible.pdf",
        stored_path=str(pdf_file),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.NEEDS_REVIEW.value,
        error="Total mismatch",
    )
    repo.add_invoice(
        doc.id,
        ExtractedInvoice(
            vendor_name="Faulty Name",
            currency="INR",
            total=Decimal("100.00"),
            overall_confidence=0.4,
        ),
    )
    session.commit()

    form_data = {
        "vendor_name": "Corrected Vendor Inc",
        "vendor_tax_id": "27AABCT1234F1Z1",
        "invoice_number": "INV-CORRECT-001",
        "invoice_date": "2026-03-22",
        "currency": "INR",
        "subtotal": "500.00",
        "tax_total": "90.00",
        "cgst": "45.00",
        "sgst": "45.00",
        "igst": "0.00",
        "total": "590.00",
        "save_as_rule": "true",
    }

    res = client.post(f"/review/{doc.id}/save", data=form_data)
    assert res.status_code == 200
    assert "Success!" in res.text

    # Verify DB record was updated
    session.expire_all()
    updated_doc = repo.get_document_by_id(doc.id)
    assert updated_doc is not None
    assert updated_doc.status == ProcessingStatus.PROCESSED.value
    assert updated_doc.error is None

    updated_inv = repo.get_invoice_by_document_id(doc.id)
    assert updated_inv is not None
    assert updated_inv.vendor_name == "Corrected Vendor Inc"
    assert updated_inv.vendor_tax_id == "27AABCT1234F1Z1"
    assert updated_inv.total == Decimal("590.00")
    assert updated_inv.overall_confidence == 1.0

    # Verify audit event
    events = repo.list_events_by_document_id(doc.id)
    assert any("review_ui" == ev.stage for ev in events)

    # Verify correction JSONL was persisted
    corrections = load_corrections(settings.corrections_dir)
    assert len(corrections) == 1
    corr = corrections[0]
    assert corr.document_id == doc.id
    assert corr.original_name == "corrigible.pdf"
    assert corr.original_fields["vendor_name"] == "Faulty Name"
    assert corr.corrected_fields["vendor_name"] == "Corrected Vendor Inc"
    assert Decimal(str(corr.corrected_fields["total"])) == Decimal("590.00")
    assert corr.save_as_rule is True
