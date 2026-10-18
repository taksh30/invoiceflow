"""Unit tests for IngestionService, SHA-256 deduplication, and storage."""

import hashlib
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from invoiceflow.db.base import create_db_engine, get_session_factory, init_db
from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.errors import IngestError
from invoiceflow.ingest import IngestionService, compute_sha256
from invoiceflow.models import DocumentSource, DocumentType, RawDocument


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
    """Provide an InvoiceRepository instance."""
    return InvoiceRepository(db_session)


def test_compute_sha256() -> None:
    """Verify SHA-256 calculation matches hashlib standard."""
    payload = b"hello invoiceflow"
    expected = hashlib.sha256(payload).hexdigest()
    assert compute_sha256(payload) == expected


def test_ingest_new_document(repo: InvoiceRepository, tmp_path: Path) -> None:
    """Verify new document is saved to raw directory and registered in database."""
    raw_dir = tmp_path / "raw"
    service = IngestionService(repository=repo, raw_dir=raw_dir)

    payload = b"%PDF-1.4 test invoice content"
    raw_doc = RawDocument(
        content=payload,
        filename="invoice_march.pdf",
        source=DocumentSource.FOLDER,
        source_ref="/path/invoice_march.pdf",
    )

    result = service.ingest(raw_doc)
    assert result.is_duplicate is False
    assert result.stored_path.exists()
    assert result.stored_path.read_bytes() == payload

    expected_hash = compute_sha256(payload)
    assert result.stored_path.name == f"{expected_hash}.pdf"
    assert result.document.file_sha256 == expected_hash
    assert result.document.doc_type == DocumentType.TEXT_PDF.value

    # Verify audit event was logged
    retrieved = repo.get_by_hash(expected_hash)
    assert retrieved is not None
    assert len(retrieved.events) == 1
    assert retrieved.events[0].stage == "ingest"


def test_ingest_duplicate_content_returns_early(repo: InvoiceRepository, tmp_path: Path) -> None:
    """Verify identical file content returns existing document without duplicate row."""
    raw_dir = tmp_path / "raw"
    service = IngestionService(repository=repo, raw_dir=raw_dir)

    payload = b"receipt-image-bytes"
    doc1 = RawDocument(
        content=payload,
        filename="receipt_1.jpg",
        source=DocumentSource.FOLDER,
        source_ref="/uploads/receipt_1.jpg",
    )
    res1 = service.ingest(doc1)
    assert res1.is_duplicate is False

    # Second document has different filename but identical payload
    doc2 = RawDocument(
        content=payload,
        filename="receipt_1_copy.jpg",
        source=DocumentSource.FOLDER,
        source_ref="/uploads/receipt_1_copy.jpg",
    )
    res2 = service.ingest(doc2)
    assert res2.is_duplicate is True
    assert res2.document.id == res1.document.id
    assert res2.stored_path == res1.stored_path


def test_ingest_unsupported_file_extension(repo: InvoiceRepository, tmp_path: Path) -> None:
    """Verify unsupported file extensions raise IngestError."""
    service = IngestionService(repository=repo, raw_dir=tmp_path / "raw")
    raw_doc = RawDocument(
        content=b"plain text notes",
        filename="notes.txt",
        source=DocumentSource.FOLDER,
        source_ref="/notes.txt",
    )

    with pytest.raises(IngestError, match="Unsupported file type"):
        service.ingest(raw_doc)
