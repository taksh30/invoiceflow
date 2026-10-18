"""End-to-end integration test running Pipeline over the benchmark fixture set."""

import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from invoiceflow.db.base import create_db_engine, get_session_factory, init_db
from invoiceflow.db.tables import DocumentRow, InvoiceRow
from invoiceflow.models import ProcessingStatus
from invoiceflow.pipeline import Pipeline

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.accuracy_report import evaluate_fixtures, print_report  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "invoices"


def _get_benchmark_files() -> list[Path]:
    """Retrieve sorted list of all 30 benchmark invoice files."""
    return [
        p
        for p in sorted(FIXTURES_DIR.iterdir())
        if p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"} and not p.name.startswith(".")
    ]


def _assert_dod_accuracy() -> None:
    """Verify that extraction accuracy across all 30 benchmark fixtures meets DoD targets."""
    accuracies, mismatches = evaluate_fixtures()
    passed = print_report(accuracies, mismatches)
    assert passed, "Extraction accuracy did not pass Definition of Done targets"
    assert accuracies["total"] >= 90.0
    assert accuracies["invoice_date"] >= 90.0
    assert accuracies["vendor_name"] >= 90.0
    assert accuracies["invoice_number"] >= 80.0
    assert accuracies["currency"] >= 90.0
    assert accuracies["vendor_tax_id"] >= 85.0


@pytest.mark.ocr
@pytest.mark.integration
def test_pipeline_e2e_full_fixtures_and_idempotency(tmp_path: Path) -> None:
    """Run full pipeline over 30 fixtures, verify accuracy, and assert zero duplicates on re-run."""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'e2e_pipeline.db'}")
    init_db(engine)
    session_factory = get_session_factory(engine)
    session: Session = session_factory()

    pipeline = Pipeline(
        session=session,
        raw_storage_dir=tmp_path / "raw_storage",
    )

    fixture_files = _get_benchmark_files()
    assert len(fixture_files) == 30, f"Expected 30 fixtures, found {len(fixture_files)}"

    # 1. First Pass: Process all 30 fixtures
    first_results = [pipeline.process_file(f) for f in fixture_files]
    assert len(first_results) == 30
    assert all(r.is_duplicate is False for r in first_results)
    assert all(
        r.status in (ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW)
        for r in first_results
    )

    # Verify initial database state
    doc_count_pass1 = session.query(DocumentRow).count()
    inv_count_pass1 = session.query(InvoiceRow).count()
    assert doc_count_pass1 == 30
    assert inv_count_pass1 == 30

    # 2. Verify Accuracy Meets Definition of Done
    _assert_dod_accuracy()

    # 3. Second Pass: Re-run the entire fixture set through the pipeline
    second_results = [pipeline.process_file(f) for f in fixture_files]
    assert len(second_results) == 30
    assert all(r.is_duplicate is True for r in second_results)

    # 4. Assert zero duplicate documents or duplicate invoices were created
    doc_count_pass2 = session.query(DocumentRow).count()
    inv_count_pass2 = session.query(InvoiceRow).count()
    assert doc_count_pass2 == 30, f"Expected 30 documents, got {doc_count_pass2}"
    assert inv_count_pass2 == 30, f"Expected 30 invoices, got {inv_count_pass2}"

    session.close()
    engine.dispose()
