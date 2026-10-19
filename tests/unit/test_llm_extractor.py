"""Unit and integration tests for LLMExtractor fallback."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from invoiceflow.db.base import Base
from invoiceflow.db.tables import DocumentRow
from invoiceflow.extract.fields import FieldExtractor
from invoiceflow.extract.llm import FakeLLMClient, LLMExtractor
from invoiceflow.extract.text import TextResult
from invoiceflow.models import DocumentSource, DocumentType, ExtractedInvoice, ProcessingStatus
from invoiceflow.pipeline import Pipeline


@pytest.fixture
def test_db_session() -> Session:
    """Create in-memory SQLite session for pipeline tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def test_llm_extractor_conforms_to_field_extractor() -> None:
    """Verify that LLMExtractor implements the FieldExtractor Protocol."""
    fake_client = FakeLLMClient()
    extractor = LLMExtractor(client=fake_client)
    assert isinstance(extractor, FieldExtractor)


def test_llm_extractor_extract_success() -> None:
    """Verify standard extraction returns FieldResult with ExtractedInvoice value."""
    fake_payload = {
        "vendor_name": "Apex Cloud Technologies",
        "vendor_tax_id": "27AAACA1234A1Z5",
        "invoice_number": "ACT-2026-999",
        "invoice_date": "2026-03-20",
        "currency": "INR",
        "subtotal": "5000.00",
        "tax_total": "900.00",
        "cgst": "450.00",
        "sgst": "450.00",
        "igst": None,
        "total": "5900.00",
    }
    client = FakeLLMClient(default_response=fake_payload)
    extractor = LLMExtractor(client=client)

    result = extractor.extract("Some noisy invoice text...")
    assert result is not None
    assert result.confidence == 0.85
    assert result.span == "llm"

    inv = result.value
    assert isinstance(inv, ExtractedInvoice)
    assert inv.vendor_name == "Apex Cloud Technologies"
    assert inv.vendor_tax_id == "27AAACA1234A1Z5"
    assert inv.invoice_number == "ACT-2026-999"
    assert str(inv.invoice_date) == "2026-03-20"
    assert inv.currency == "INR"
    assert inv.total == Decimal("5900.00")
    assert inv.subtotal == Decimal("5000.00")
    assert inv.tax_total == Decimal("900.00")
    assert inv.overall_confidence == 0.85


def test_llm_extractor_markdown_fence_cleaning() -> None:
    """Verify markdown code fences are stripped before JSON parsing."""
    raw_markdown = '```json\n{"vendor_name": "Fence Corp", "total": "150.00"}\n```'
    client = FakeLLMClient(default_response=raw_markdown)
    extractor = LLMExtractor(client=client)

    inv = extractor.extract_invoice("Sample text")
    assert inv is not None
    assert inv.vendor_name == "Fence Corp"
    assert inv.total == Decimal("150.00")


def test_llm_extractor_timeout_handling() -> None:
    """Verify TimeoutError is caught and handled gracefully returning None."""
    client = FakeLLMClient(should_timeout=True)
    extractor = LLMExtractor(client=client, timeout=5.0)

    result = extractor.extract("Sample text")
    assert result is None
    assert client.call_count == 1


def test_llm_extractor_failure_handling() -> None:
    """Verify runtime provider failures return None without uncaught exceptions."""
    client = FakeLLMClient(should_fail=True, error_message="API Rate limit exceeded")
    extractor = LLMExtractor(client=client)

    result = extractor.extract("Sample text")
    assert result is None


def test_llm_extractor_malformed_json() -> None:
    """Verify malformed JSON responses return None safely."""
    client = FakeLLMClient(default_response="Not a JSON string at all")
    extractor = LLMExtractor(client=client)

    result = extractor.extract("Sample text")
    assert result is None


def test_llm_cost_calculation_and_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verify token cost calculation and structured logging output."""
    client = FakeLLMClient(
        prompt_tokens=1000,
        completion_tokens=500,
        cost=Decimal("0.00045"),
        model="gpt-4o-mini",
    )
    extractor = LLMExtractor(client=client, model="gpt-4o-mini")

    with caplog.at_level("INFO"):
        res = extractor.extract("Test invoice text")

    assert res is not None
    assert any(
        "LLM extraction completed successfully" in record.message for record in caplog.records
    )


def test_pipeline_fallback_triggered_on_low_confidence(
    tmp_path: Path, test_db_session: Session
) -> None:
    """Verify pipeline invokes LLMExtractor only when overall_confidence < 0.6."""
    fake_client = FakeLLMClient(
        default_response={
            "vendor_name": "Rescued Vendor",
            "invoice_number": "INV-RESCUED-101",
            "invoice_date": "2026-03-25",
            "currency": "INR",
            "subtotal": "2000.00",
            "tax_total": "360.00",
            "total": "2360.00",
        }
    )
    llm_extractor = LLMExtractor(client=fake_client)

    pipeline = Pipeline(
        session=test_db_session,
        raw_storage_dir=tmp_path / "raw",
        llm_extractor=llm_extractor,
        llm_enabled=True,
        llm_confidence_threshold=0.6,
    )

    # Mock text extractor and field extractor to simulate low confidence
    low_conf_invoice = ExtractedInvoice(
        vendor_name="Unknown Vendor",
        invoice_number=None,
        invoice_date=None,
        currency="INR",
        total=Decimal("0.01"),
        confidence={"vendor_name": 0.4, "total": 0.4, "invoice_date": 0.4},
        overall_confidence=0.4,
    )

    test_file = tmp_path / "noisy_receipt.pdf"
    test_file.write_bytes(b"%PDF-1.4 simulated receipt")

    doc = DocumentRow(
        file_sha256="abc1234567890def",
        original_name="noisy_receipt.pdf",
        stored_path=str(test_file),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.PROCESSED.value,
    )
    test_db_session.add(doc)
    test_db_session.commit()

    pipeline.extractor.extract_fields = MagicMock(return_value=low_conf_invoice)  # type: ignore[method-assign]

    with patch(
        "invoiceflow.pipeline.extract_text",
        return_value=TextResult(raw_text="Noisy text", method="text_pdf", words=[], pages=1),
    ):
        result = pipeline._process_pipeline_stages(doc, test_file)

    assert fake_client.call_count == 1
    assert result.invoice is not None
    assert result.invoice.vendor_name == "Rescued Vendor"
    assert result.invoice.total == Decimal("2360.00")


def test_pipeline_fallback_bypassed_on_high_confidence(
    tmp_path: Path, test_db_session: Session
) -> None:
    """Verify pipeline does NOT invoke LLMExtractor when overall_confidence >= 0.6."""
    fake_client = FakeLLMClient()
    llm_extractor = LLMExtractor(client=fake_client)

    pipeline = Pipeline(
        session=test_db_session,
        raw_storage_dir=tmp_path / "raw",
        llm_extractor=llm_extractor,
        llm_enabled=True,
        llm_confidence_threshold=0.6,
    )

    high_conf_invoice = ExtractedInvoice(
        vendor_name="Clear Vendor Ltd",
        invoice_number="INV-CLEAN-01",
        invoice_date=None,
        currency="INR",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("18.00"),
        total=Decimal("118.00"),
        confidence={"vendor_name": 0.95, "total": 0.95, "invoice_date": 0.95},
        overall_confidence=0.95,
    )

    test_file = tmp_path / "clean_invoice.pdf"
    test_file.write_bytes(b"%PDF-1.4 clean invoice")

    doc = DocumentRow(
        file_sha256="clean1234567890def",
        original_name="clean_invoice.pdf",
        stored_path=str(test_file),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.PROCESSED.value,
    )
    test_db_session.add(doc)
    test_db_session.commit()

    pipeline.extractor.extract_fields = MagicMock(return_value=high_conf_invoice)  # type: ignore[method-assign]

    with patch(
        "invoiceflow.pipeline.extract_text",
        return_value=TextResult(raw_text="Clean text", method="text_pdf", words=[], pages=1),
    ):
        result = pipeline._process_pipeline_stages(doc, test_file)

    # LLM must not be called
    assert fake_client.call_count == 0
    assert result.invoice is not None
    assert result.invoice.vendor_name == "Clear Vendor Ltd"


def test_pipeline_fallback_disabled_flag(tmp_path: Path, test_db_session: Session) -> None:
    """Verify pipeline does NOT invoke LLMExtractor when llm_enabled is False."""
    fake_client = FakeLLMClient()
    llm_extractor = LLMExtractor(client=fake_client)

    pipeline = Pipeline(
        session=test_db_session,
        raw_storage_dir=tmp_path / "raw",
        llm_extractor=llm_extractor,
        llm_enabled=False,  # Disabled via config flag
        llm_confidence_threshold=0.6,
    )

    low_conf_invoice = ExtractedInvoice(
        vendor_name="Unknown Vendor",
        invoice_number=None,
        invoice_date=None,
        currency="INR",
        total=Decimal("0.01"),
        confidence={"vendor_name": 0.3, "total": 0.3, "invoice_date": 0.3},
        overall_confidence=0.3,
    )

    test_file = tmp_path / "disabled_test.pdf"
    test_file.write_bytes(b"%PDF-1.4 test")

    doc = DocumentRow(
        file_sha256="dis1234567890def",
        original_name="disabled_test.pdf",
        stored_path=str(test_file),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.PROCESSED.value,
    )
    test_db_session.add(doc)
    test_db_session.commit()

    pipeline.extractor.extract_fields = MagicMock(return_value=low_conf_invoice)  # type: ignore[method-assign]

    with patch(
        "invoiceflow.pipeline.extract_text",
        return_value=TextResult(raw_text="Noisy text", method="text_pdf", words=[], pages=1),
    ):
        result = pipeline._process_pipeline_stages(doc, test_file)

    assert fake_client.call_count == 0
    assert result.invoice is not None
    assert result.invoice.vendor_name == "Unknown Vendor"


def test_pipeline_fallback_error_isolation(tmp_path: Path, test_db_session: Session) -> None:
    """Verify pipeline isolates LLM failures and logs audit event without failing pipeline."""
    failing_client = FakeLLMClient(should_fail=True, error_message="LLM service unavailable")
    llm_extractor = LLMExtractor(client=failing_client)

    pipeline = Pipeline(
        session=test_db_session,
        raw_storage_dir=tmp_path / "raw",
        llm_extractor=llm_extractor,
        llm_enabled=True,
        llm_confidence_threshold=0.6,
    )

    low_conf_invoice = ExtractedInvoice(
        vendor_name="Partial Vendor",
        invoice_number=None,
        invoice_date=None,
        currency="INR",
        total=Decimal("0.01"),
        confidence={"vendor_name": 0.3, "total": 0.3, "invoice_date": 0.3},
        overall_confidence=0.3,
    )

    test_file = tmp_path / "err_test.pdf"
    test_file.write_bytes(b"%PDF-1.4 err test")

    doc = DocumentRow(
        file_sha256="err1234567890def",
        original_name="err_test.pdf",
        stored_path=str(test_file),
        source=DocumentSource.FOLDER.value,
        source_ref="test",
        doc_type=DocumentType.TEXT_PDF.value,
        status=ProcessingStatus.PROCESSED.value,
    )
    test_db_session.add(doc)
    test_db_session.commit()

    pipeline.extractor.extract_fields = MagicMock(return_value=low_conf_invoice)  # type: ignore[method-assign]

    with patch(
        "invoiceflow.pipeline.extract_text",
        return_value=TextResult(raw_text="Error text", method="text_pdf", words=[], pages=1),
    ):
        result = pipeline._process_pipeline_stages(doc, test_file)

    assert failing_client.call_count == 1
    # Document should not crash with status=FAILED due to LLM error;
    # it falls back to low_conf_invoice
    assert result.invoice is not None
    assert result.invoice.vendor_name == "Partial Vendor"

    # Verify audit event was recorded for the failed fallback
    events = pipeline.repo.list_events_by_document_id(doc.id)
    assert any("llm_fallback" == ev.stage for ev in events)
