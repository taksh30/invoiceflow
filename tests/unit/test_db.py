"""Unit tests for SQLAlchemy 2.0 database tables and InvoiceRepository."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoiceflow.db.base import create_db_engine, get_session_factory, init_db
from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.models import DocumentSource, DocumentType, ExtractedInvoice, ProcessingStatus


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory SQLite database session."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def repo(db_session: Session) -> InvoiceRepository:
    """Provide an InvoiceRepository instance bound to the in-memory session."""
    return InvoiceRepository(db_session)


def test_add_and_get_document_by_hash(repo: InvoiceRepository) -> None:
    """Verify document creation and retrieval by content SHA-256."""
    doc = repo.add_document(
        file_sha256="abc123hash",
        original_name="invoice_01.pdf",
        stored_path="data/raw/abc123hash.pdf",
        source=DocumentSource.FOLDER,
        source_ref="/uploads/invoice_01.pdf",
        doc_type=DocumentType.TEXT_PDF,
        status=ProcessingStatus.PROCESSED,
    )
    assert doc.id is not None
    assert doc.file_sha256 == "abc123hash"

    retrieved = repo.get_by_hash("abc123hash")
    assert retrieved is not None
    assert retrieved.id == doc.id
    assert retrieved.original_name == "invoice_01.pdf"

    assert repo.get_by_hash("nonexistent") is None


def test_document_unique_hash_constraint(repo: InvoiceRepository) -> None:
    """Verify duplicate file_sha256 values are rejected by DB constraint."""
    repo.add_document(
        file_sha256="dup_hash",
        original_name="f1.pdf",
        stored_path="data/raw/f1.pdf",
        source=DocumentSource.FOLDER,
        source_ref="/f1.pdf",
        doc_type=DocumentType.TEXT_PDF,
    )
    with pytest.raises(IntegrityError):
        repo.add_document(
            file_sha256="dup_hash",
            original_name="f2.pdf",
            stored_path="data/raw/f2.pdf",
            source=DocumentSource.FOLDER,
            source_ref="/f2.pdf",
            doc_type=DocumentType.TEXT_PDF,
        )


def test_add_invoice_with_relationships(repo: InvoiceRepository) -> None:
    """Verify invoice insertion and 1:1 relationship with document."""
    doc = repo.add_document(
        file_sha256="inv_hash",
        original_name="inv.pdf",
        stored_path="data/raw/inv.pdf",
        source=DocumentSource.EMAIL,
        source_ref="msg-id-100",
        doc_type=DocumentType.TEXT_PDF,
    )

    inv_model = ExtractedInvoice(
        vendor_name="Tata Power",
        vendor_tax_id="27AAACT2727Q1ZW",
        invoice_number="TP-2024-88",
        invoice_date=date(2024, 5, 10),
        currency="INR",
        subtotal=Decimal("2000.00"),
        tax_total=Decimal("360.00"),
        cgst=Decimal("180.00"),
        sgst=Decimal("180.00"),
        total=Decimal("2360.00"),
        confidence={"total": 0.95, "vendor_name": 0.92},
        overall_confidence=0.935,
    )

    inv_row = repo.add_invoice(doc.id, inv_model)
    assert inv_row.id is not None
    assert inv_row.document_id == doc.id
    assert inv_row.vendor_name == "Tata Power"
    assert inv_row.total == Decimal("2360.00")
    assert inv_row.confidence["total"] == 0.95

    # Check relationship navigation
    assert doc.invoice is not None
    assert doc.invoice.id == inv_row.id
    assert inv_row.document.original_name == "inv.pdf"


def test_find_candidates(repo: InvoiceRepository) -> None:
    """Verify candidate search by invoice number or vendor + total/date."""
    d1 = repo.add_document("h1", "f1.pdf", "p1", "folder", "r1", "text_pdf")
    d2 = repo.add_document("h2", "f2.pdf", "p2", "folder", "r2", "text_pdf")

    inv1 = ExtractedInvoice(
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        invoice_date=date(2024, 3, 1),
        total=Decimal("500.00"),
    )
    inv2 = ExtractedInvoice(
        vendor_name="Beta Ltd",
        invoice_number="INV-002",
        invoice_date=date(2024, 3, 15),
        total=Decimal("750.00"),
    )
    repo.add_invoice(d1.id, inv1)
    repo.add_invoice(d2.id, inv2)

    # Match by invoice_number
    res1 = repo.find_candidates(invoice_number="INV-001")
    assert len(res1) == 1
    assert res1[0].vendor_name == "Acme Corp"

    # Match by vendor and total
    res2 = repo.find_candidates(vendor_name="Beta Ltd", total=Decimal("750.00"))
    assert len(res2) == 1
    assert res2[0].invoice_number == "INV-002"

    # Non-match
    res3 = repo.find_candidates(invoice_number="INV-999")
    assert len(res3) == 0


def test_list_by_month(repo: InvoiceRepository) -> None:
    """Verify monthly querying and date ordering."""
    dates = [
        ("h_apr", date(2024, 4, 30), Decimal("100.00")),
        ("h_may1", date(2024, 5, 2), Decimal("200.00")),
        ("h_may2", date(2024, 5, 25), Decimal("300.00")),
        ("h_jun", date(2024, 6, 1), Decimal("400.00")),
    ]

    for h, dt, tot in dates:
        doc = repo.add_document(h, f"{h}.pdf", f"p_{h}", "folder", "r", "text_pdf")
        inv = ExtractedInvoice(
            vendor_name="Vendor",
            invoice_date=dt,
            total=tot,
        )
        repo.add_invoice(doc.id, inv)

    may_records = repo.list_by_month(year=2024, month=5)
    assert len(may_records) == 2
    assert may_records[0].invoice_date == date(2024, 5, 2)
    assert may_records[1].invoice_date == date(2024, 5, 25)


def test_log_event(repo: InvoiceRepository) -> None:
    """Verify audit log event persistence."""
    doc = repo.add_document("ev_hash", "doc.pdf", "path", "folder", "ref", "text_pdf")
    event = repo.log_event(
        document_id=doc.id,
        stage="ocr",
        message="Text extracted with 98% confidence",
        level="INFO",
    )
    assert event.id is not None
    assert event.stage == "ocr"
    assert event.level == "INFO"
    assert len(doc.events) == 1
    assert doc.events[0].id == event.id
