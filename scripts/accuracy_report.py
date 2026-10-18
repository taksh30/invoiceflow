"""Accuracy evaluation harness benchmarking field extraction against ground truth fixtures."""

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoiceflow.extract.fields import InvoiceFieldsExtractor
from invoiceflow.extract.text import extract_text

FIXTURES_DIR = Path("tests/fixtures/invoices")


def evaluate_fixtures() -> tuple[dict[str, float], list[dict[str, str]]]:
    """Evaluate extraction accuracy across all benchmark fixtures."""
    extractor = InvoiceFieldsExtractor()
    doc_paths = [
        p
        for p in sorted(FIXTURES_DIR.iterdir())
        if p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"} and not p.name.startswith(".")
    ]

    field_counts = {
        "total": 0,
        "invoice_date": 0,
        "vendor_name": 0,
        "invoice_number": 0,
        "currency": 0,
        "vendor_tax_id": 0,
    }
    field_totals = {
        "total": 0,
        "invoice_date": 0,
        "vendor_name": 0,
        "invoice_number": 0,
        "currency": 0,
        "vendor_tax_id": 0,
    }

    mismatches: list[dict[str, str]] = []

    for doc_path in doc_paths:
        expected_path = doc_path.with_suffix(".expected.json")
        if not expected_path.exists():
            continue

        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        locale = "US" if "_us_" in doc_path.name else ("EU" if "_eu_" in doc_path.name else "IN")

        text_res = extract_text(doc_path)
        extracted = extractor.extract_fields(text_res, locale=locale)

        # 1. Total
        field_totals["total"] += 1
        exp_total = Decimal(expected["total"])
        if extracted.total == exp_total:
            field_counts["total"] += 1
        else:
            mismatches.append(
                {
                    "doc": doc_path.name,
                    "field": "total",
                    "expected": str(exp_total),
                    "actual": str(extracted.total),
                }
            )

        # 2. Date
        field_totals["invoice_date"] += 1
        exp_date = date.fromisoformat(expected["invoice_date"])
        if extracted.invoice_date == exp_date:
            field_counts["invoice_date"] += 1
        else:
            mismatches.append(
                {
                    "doc": doc_path.name,
                    "field": "invoice_date",
                    "expected": str(exp_date),
                    "actual": str(extracted.invoice_date),
                }
            )

        # 3. Vendor
        field_totals["vendor_name"] += 1
        exp_vendor = expected["vendor_name"].strip().lower()
        act_vendor = extracted.vendor_name.strip().lower()
        if exp_vendor in act_vendor or act_vendor in exp_vendor:
            field_counts["vendor_name"] += 1
        else:
            mismatches.append(
                {
                    "doc": doc_path.name,
                    "field": "vendor_name",
                    "expected": expected["vendor_name"],
                    "actual": extracted.vendor_name,
                }
            )

        # 4. Invoice Number
        if expected.get("invoice_number"):
            field_totals["invoice_number"] += 1
            exp_num = expected["invoice_number"].strip()
            act_num = (extracted.invoice_number or "").strip()
            if exp_num == act_num:
                field_counts["invoice_number"] += 1

        # 5. Currency
        if expected.get("currency"):
            field_totals["currency"] += 1
            if extracted.currency == expected["currency"]:
                field_counts["currency"] += 1

        # 6. Tax ID
        if expected.get("vendor_tax_id"):
            field_totals["vendor_tax_id"] += 1
            if extracted.vendor_tax_id == expected["vendor_tax_id"]:
                field_counts["vendor_tax_id"] += 1

    accuracies = {
        k: (field_counts[k] / field_totals[k] * 100.0) if field_totals[k] > 0 else 0.0
        for k in field_counts
    }
    return accuracies, mismatches


def print_report(accuracies: dict[str, float], mismatches: list[dict[str, str]]) -> bool:
    """Print markdown formatted accuracy report table and check against DoD thresholds."""
    print("\n## Field Extraction Accuracy Report")
    print("| Field | Accuracy | Target | Status |")
    print("| :--- | :--- | :--- | :--- |")

    targets = {
        "total": 90.0,
        "invoice_date": 90.0,
        "vendor_name": 90.0,
        "invoice_number": 80.0,
        "currency": 90.0,
        "vendor_tax_id": 85.0,
    }

    all_passed = True
    for field, target in targets.items():
        acc = accuracies.get(field, 0.0)
        passed = acc >= target
        status = "PASSED" if passed else "FAILED"
        if not passed and field in {"total", "invoice_date", "vendor_name"}:
            all_passed = False
        print(f"| **{field}** | {acc:.1f}% | >= {target:.0f}% | {status} |")

    if mismatches:
        print(f"\nMismatches ({len(mismatches)} total):")
        for m in mismatches[:10]:
            print(f"- {m['doc']} [{m['field']}]: expected {m['expected']!r}, got {m['actual']!r}")

    return all_passed


if __name__ == "__main__":
    accs, mismatches = evaluate_fixtures()
    passed = print_report(accs, mismatches)
    sys.exit(0 if passed else 1)
