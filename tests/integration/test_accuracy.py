import sys
from pathlib import Path

import pytest

# Ensure scripts directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.accuracy_report import evaluate_fixtures  # noqa: E402


@pytest.mark.ocr
def test_30_fixtures_accuracy_meets_dod() -> None:
    """Benchmark extraction across 30 fixtures and ensure DoD targets are met."""
    accuracies, _ = evaluate_fixtures()

    # Targets defined in docs/01-PROJECT.md Definition of Done (MVP)
    assert accuracies["total"] >= 90.0, f"Total acc {accuracies['total']}% < 90%"
    assert accuracies["invoice_date"] >= 90.0, f"Date acc {accuracies['invoice_date']}% < 90%"
    assert accuracies["vendor_name"] >= 90.0, f"Vendor acc {accuracies['vendor_name']}% < 90%"
    assert accuracies["invoice_number"] >= 80.0, (
        f"Invoice number acc {accuracies['invoice_number']}% < 80%"
    )
    assert accuracies["currency"] >= 90.0, f"Currency acc {accuracies['currency']}% < 90%"
    assert accuracies["vendor_tax_id"] >= 85.0, f"Tax ID acc {accuracies['vendor_tax_id']}% < 85%"
