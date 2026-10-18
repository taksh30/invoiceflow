"""Unit tests for the end-to-end Pipeline orchestrator."""

from collections.abc import Generator
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from invoiceflow.db.base import create_db_engine, get_session_factory, init_db
from invoiceflow.db.tables import DocumentRow, InvoiceRow
from invoiceflow.models import DocumentSource, ProcessingStatus, RawDocument
from invoiceflow.pipeline import Pipeline, PipelineResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "invoices"


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
def pipeline(db_session: Session, tmp_path: Path) -> Pipeline:
    """Create a Pipeline instance with in-memory DB and temporary raw storage."""
    return Pipeline(session=db_session, raw_storage_dir=tmp_path / "raw")


def test_process_file_success(pipeline: Pipeline, db_session: Session) -> None:
    """Verify processing a valid invoice PDF end-to-end."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    assert sample_file.exists()

    result = pipeline.process_file(sample_file)

    assert isinstance(result, PipelineResult)
    assert result.status in (ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW)
    assert result.is_duplicate is False
    assert result.invoice is not None
    assert result.invoice.total == Decimal("1180.00")
    assert result.invoice.currency == "INR"
    assert "Reliance Retail" in result.invoice.vendor_name

    # Check database persistence
    doc = db_session.get(DocumentRow, result.document.id)
    assert doc is not None
    assert doc.status == result.status.value

    inv = db_session.get(InvoiceRow, result.invoice.id)
    assert inv is not None
    assert inv.total == Decimal("1180.00")

    # Check audit events logged
    events = pipeline.repo.list_events_by_document_id(result.document.id)
    stages = [ev.stage for ev in events]
    assert "ingest" in stages
    assert "classify" in stages
    assert "extract_text" in stages
    assert "extract_fields" in stages
    assert "validate" in stages
    assert "persist" in stages


def test_process_file_exact_duplicate_hash(pipeline: Pipeline, db_session: Session) -> None:
    """Verify exact file content duplicates are detected at ingest without new inserts."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"

    res1 = pipeline.process_file(sample_file)
    assert res1.is_duplicate is False

    res2 = pipeline.process_file(sample_file)
    assert res2.is_duplicate is True
    assert res2.document.id == res1.document.id
    assert res2.invoice is not None
    assert res2.invoice.id == res1.invoice.id  # type: ignore[union-attr]

    # Exactly 1 DocumentRow and 1 InvoiceRow should exist
    docs = db_session.query(DocumentRow).all()
    invoices = db_session.query(InvoiceRow).all()
    assert len(docs) == 1
    assert len(invoices) == 1


def test_process_raw_document_fuzzy_duplicate(pipeline: Pipeline, db_session: Session) -> None:
    """Verify fuzzy duplicate detection flags duplicate_of and DUPLICATE status."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    content = sample_file.read_bytes()

    # Process first document
    raw1 = RawDocument(
        content=content,
        filename="inv_orig.pdf",
        source=DocumentSource.FOLDER,
        source_ref="test/inv_orig.pdf",
    )
    res1 = pipeline.process_raw_document(raw1)
    assert res1.status in (ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW)

    # Process second document with slightly altered bytes (different hash) but same invoice data
    altered_content = content + b"\n% appended dummy comment"
    raw2 = RawDocument(
        content=altered_content,
        filename="inv_copy.pdf",
        source=DocumentSource.FOLDER,
        source_ref="test/inv_copy.pdf",
    )
    res2 = pipeline.process_raw_document(raw2)

    assert res2.status == ProcessingStatus.DUPLICATE
    assert res2.is_duplicate is True
    assert res2.invoice is not None
    assert res2.invoice.duplicate_of == res1.invoice.id  # type: ignore[union-attr]


def test_error_isolation_on_corrupted_file(pipeline: Pipeline, db_session: Session) -> None:
    """Verify unhandled classification errors mark document FAILED and do not raise."""
    corrupt_raw = RawDocument(
        content=b"Corrupted non-PDF header bytes %PDF-99999",
        filename="corrupted.pdf",
        source=DocumentSource.FOLDER,
        source_ref="test/corrupted.pdf",
    )

    result = pipeline.process_raw_document(corrupt_raw)

    assert result.status == ProcessingStatus.FAILED
    assert result.error is not None
    assert "Failed to classify" in result.error
    assert result.invoice is None

    # Verify document status in DB is failed
    doc = db_session.get(DocumentRow, result.document.id)
    assert doc is not None
    assert doc.status == "failed"

    # Verify ERROR event logged
    events = pipeline.repo.list_events_by_document_id(result.document.id)
    error_events = [e for e in events if e.level == "ERROR"]
    assert len(error_events) >= 1
    assert "Classification failed" in error_events[0].message


def test_error_isolation_on_extraction_exception(pipeline: Pipeline, db_session: Session) -> None:
    """Verify unhandled extraction errors mark document FAILED and do not raise."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    content = sample_file.read_bytes()
    raw = RawDocument(
        content=content,
        filename="valid_format_failing_text.pdf",
        source=DocumentSource.FOLDER,
        source_ref="test/valid_format_failing_text.pdf",
    )

    with patch("invoiceflow.pipeline.extract_text", side_effect=RuntimeError("Parsing exploded")):
        result = pipeline.process_raw_document(raw)

    assert result.status == ProcessingStatus.FAILED
    assert result.error is not None
    assert "Parsing exploded" in result.error
    assert result.invoice is None

    # Verify document status in DB is failed
    doc = db_session.get(DocumentRow, result.document.id)
    assert doc is not None
    assert doc.status == "failed"

    # Verify ERROR event logged
    events = pipeline.repo.list_events_by_document_id(result.document.id)
    error_events = [e for e in events if e.level == "ERROR"]
    assert len(error_events) >= 1
    assert "Parsing exploded" in error_events[0].message


def test_process_folder(pipeline: Pipeline, tmp_path: Path) -> None:
    """Verify process_folder scans and processes all supported files in folder."""
    folder = tmp_path / "invoices_batch"
    folder.mkdir()

    # Copy 2 files into the folder
    f1 = folder / "inv_01.pdf"
    f2 = folder / "inv_02.pdf"
    f1.write_bytes((FIXTURES_DIR / "inv_in_01.pdf").read_bytes())
    f2.write_bytes((FIXTURES_DIR / "inv_in_02.pdf").read_bytes())

    results = pipeline.process_folder(folder)
    assert len(results) == 2
    assert all(
        r.status in (ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW) for r in results
    )


def test_reprocess_document_success(pipeline: Pipeline, db_session: Session) -> None:
    """Verify reprocess_document clears old invoice row and re-executes pipeline."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    res1 = pipeline.process_file(sample_file)

    reprocessed_res = pipeline.reprocess_document(res1.document.id)

    assert reprocessed_res.status in (ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW)
    assert reprocessed_res.invoice is not None

    # Verify audit event logged for reprocessing
    events = pipeline.repo.list_events_by_document_id(res1.document.id)
    reprocess_events = [e for e in events if "Reprocessing document" in e.message]
    assert len(reprocess_events) == 1

    # Verify exactly 1 invoice exists for this document in the database
    invoices = pipeline.repo.get_invoice_by_document_id(res1.document.id)
    assert invoices is not None
    assert invoices.id == reprocessed_res.invoice.id

    # Verify only 1 invoice exists for this document
    invoices = pipeline.repo.get_invoice_by_document_id(res1.document.id)
    assert invoices is not None
    assert invoices.id == reprocessed_res.invoice.id


def test_reprocess_nonexistent_document_raises(pipeline: Pipeline) -> None:
    """Verify reprocess_document raises ValueError when document does not exist."""
    with pytest.raises(ValueError, match="Document with ID 999999 not found"):
        pipeline.reprocess_document(999999)
