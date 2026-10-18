"""Unit tests for deduplication engine and fuzzy matching rules."""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from invoiceflow.db.base import Base
from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.db.tables import DocumentRow
from invoiceflow.dedupe import (
    DeduplicationResult,
    find_duplicate,
    normalize_vendor,
    vendor_similarity,
)
from invoiceflow.models import DocumentSource, DocumentType, ExtractedInvoice, ProcessingStatus


def _create_test_repo() -> tuple[Session, InvoiceRepository]:
    """Create in-memory SQLite database session and repository."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    repo = InvoiceRepository(session)
    return session, repo


def _create_sample_doc(session: Session, sha: str = "abc123") -> DocumentRow:
    """Create a sample DocumentRow in the test database."""
    doc = DocumentRow(
        file_sha256=sha,
        original_name="test.pdf",
        stored_path="data/raw/test.pdf",
        source=DocumentSource.FOLDER,
        source_ref="/invoices",
        doc_type=DocumentType.TEXT_PDF,
        status=ProcessingStatus.PROCESSED,
    )
    session.add(doc)
    session.flush()
    return doc


def test_normalize_vendor() -> None:
    """Test vendor name normalization strips legal suffixes and punctuation."""
    assert normalize_vendor("Tata Consultancy Services Ltd.") == "tata consultancy services"
    assert normalize_vendor("Amazon Web Services, Inc.") == "amazon web services"
    assert normalize_vendor("Acme Solutions Pvt Ltd") == "acme solutions"
    assert normalize_vendor("Google LLC") == "google"


def test_vendor_similarity() -> None:
    """Test fuzzy similarity scoring using rapidfuzz."""
    sim = vendor_similarity("Tata Consultancy Services", "Tata Consultancy Services Ltd")
    assert sim >= 90.0

    diff_sim = vendor_similarity("Tata Consultancy Services", "Wipro Enterprises")
    assert diff_sim < 50.0


def test_find_duplicate_exact_match() -> None:
    """Exact match on vendor, number, total, and date is marked as duplicate."""
    session, repo = _create_test_repo()
    doc = _create_sample_doc(session, sha="sha_01")

    orig_invoice = ExtractedInvoice(
        vendor_name="Reliance Retail Ltd",
        invoice_number="INV-2024-001",
        invoice_date=date(2024, 5, 15),
        total=Decimal("1180.00"),
        currency="INR",
    )
    saved_row = repo.add_invoice(doc.id, orig_invoice)

    # Identical incoming invoice
    dup_candidate = ExtractedInvoice(
        vendor_name="Reliance Retail Ltd",
        invoice_number="INV-2024-001",
        invoice_date=date(2024, 5, 15),
        total=Decimal("1180.00"),
        currency="INR",
    )

    result = find_duplicate(dup_candidate, repo)
    assert result.is_duplicate is True
    assert result.duplicate_of_id == saved_row.id
    assert result.status == ProcessingStatus.DUPLICATE
    assert "Fuzzy duplicate" in (result.reason or "")


def test_find_duplicate_rescanned_copy_fuzzy_vendor() -> None:
    """Re-scanned copy with slight vendor OCR variation is marked duplicate."""
    session, repo = _create_test_repo()
    doc = _create_sample_doc(session, sha="sha_02")

    orig_invoice = ExtractedInvoice(
        vendor_name="Tata Consultancy Services Ltd",
        invoice_number="TCS-9942",
        invoice_date=date(2024, 4, 12),
        total=Decimal("59000.00"),
        currency="INR",
    )
    saved_row = repo.add_invoice(doc.id, orig_invoice)

    # Re-scanned copy missing "Ltd"
    rescan_invoice = ExtractedInvoice(
        vendor_name="Tata Consultancy Services",
        invoice_number="TCS-9942",
        invoice_date=date(2024, 4, 12),
        total=Decimal("59000.00"),
        currency="INR",
    )

    result = find_duplicate(rescan_invoice, repo)
    assert result.is_duplicate is True
    assert result.duplicate_of_id == saved_row.id
    assert result.status == ProcessingStatus.DUPLICATE


def test_find_duplicate_near_miss_different_invoice_number() -> None:
    """Same vendor and total, but different invoice number is NOT duplicate."""
    session, repo = _create_test_repo()
    doc = _create_sample_doc(session, sha="sha_03")

    orig_invoice = ExtractedInvoice(
        vendor_name="Zomato Limited",
        invoice_number="ZOM-4512",
        invoice_date=date(2024, 5, 18),
        total=Decimal("472.50"),
        currency="INR",
    )
    repo.add_invoice(doc.id, orig_invoice)

    # Different invoice number
    new_invoice = ExtractedInvoice(
        vendor_name="Zomato Limited",
        invoice_number="ZOM-4513",
        invoice_date=date(2024, 5, 18),
        total=Decimal("472.50"),
        currency="INR",
    )

    result = find_duplicate(new_invoice, repo)
    assert result.is_duplicate is False
    assert result.duplicate_of_id is None
    assert result.status == ProcessingStatus.PROCESSED


def test_find_duplicate_near_miss_different_total() -> None:
    """Same vendor and invoice number, but different total is NOT duplicate."""
    session, repo = _create_test_repo()
    doc = _create_sample_doc(session, sha="sha_04")

    orig_invoice = ExtractedInvoice(
        vendor_name="Swiggy India",
        invoice_number="SWG-1102",
        invoice_date=date(2024, 5, 22),
        total=Decimal("630.00"),
        currency="INR",
    )
    repo.add_invoice(doc.id, orig_invoice)

    # Different total
    diff_total_invoice = ExtractedInvoice(
        vendor_name="Swiggy India",
        invoice_number="SWG-1102",
        invoice_date=date(2024, 5, 22),
        total=Decimal("850.00"),
        currency="INR",
    )

    result = find_duplicate(diff_total_invoice, repo)
    assert result.is_duplicate is False
    assert result.duplicate_of_id is None


def test_find_duplicate_near_miss_different_vendor() -> None:
    """Same total and date, but different vendor is NOT duplicate."""
    session, repo = _create_test_repo()
    doc = _create_sample_doc(session, sha="sha_05")

    orig_invoice = ExtractedInvoice(
        vendor_name="Infosys Limited",
        invoice_number="INF-2024-10",
        invoice_date=date(2024, 5, 20),
        total=Decimal("25000.00"),
        currency="INR",
    )
    repo.add_invoice(doc.id, orig_invoice)

    # Completely different vendor with same amount and date
    diff_vendor_invoice = ExtractedInvoice(
        vendor_name="Wipro Enterprises",
        invoice_number="WIP-9912",
        invoice_date=date(2024, 5, 20),
        total=Decimal("25000.00"),
        currency="INR",
    )

    result = find_duplicate(diff_vendor_invoice, repo)
    assert result.is_duplicate is False
    assert result.duplicate_of_id is None


def test_find_duplicate_empty_repo() -> None:
    """When repo has no candidates, returns non-duplicate result cleanly."""
    _, repo = _create_test_repo()

    invoice = ExtractedInvoice(
        vendor_name="Adobe Systems",
        invoice_number="ADB-7741",
        invoice_date=date(2024, 5, 22),
        total=Decimal("57.23"),
        currency="USD",
    )

    result = find_duplicate(invoice, repo)
    assert isinstance(result, DeduplicationResult)
    assert result.is_duplicate is False
    assert result.duplicate_of_id is None


def test_find_duplicate_missing_invoice_number_matches_on_date_and_total() -> None:
    """Receipts without invoice numbers duplicate if vendor, total, and date match."""
    session, repo = _create_test_repo()
    doc = _create_sample_doc(session, sha="sha_06")

    orig_receipt = ExtractedInvoice(
        vendor_name="Starbucks Coffee",
        invoice_number=None,
        invoice_date=date(2024, 6, 1),
        total=Decimal("450.00"),
        currency="INR",
    )
    saved = repo.add_invoice(doc.id, orig_receipt)

    dup_receipt = ExtractedInvoice(
        vendor_name="Starbucks Coffee",
        invoice_number=None,
        invoice_date=date(2024, 6, 1),
        total=Decimal("450.00"),
        currency="INR",
    )
    result = find_duplicate(dup_receipt, repo)
    assert result.is_duplicate is True
    assert result.duplicate_of_id == saved.id

    # Different date does not match
    diff_date_receipt = ExtractedInvoice(
        vendor_name="Starbucks Coffee",
        invoice_number=None,
        invoice_date=date(2024, 6, 2),
        total=Decimal("450.00"),
        currency="INR",
    )
    assert find_duplicate(diff_date_receipt, repo).is_duplicate is False


def test_vendor_similarity_empty_strings() -> None:
    """Empty vendor strings return 0.0 similarity."""
    assert vendor_similarity("", "Vendor") == 0.0
    assert vendor_similarity("Vendor", "") == 0.0
