"""QuickBooks IIF and CSV export generators."""

import csv
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from invoiceflow.db.tables import InvoiceRow


class QuickBooksMappingConfig(BaseModel):
    """Configuration mapping for QuickBooks IIF and CSV exports."""

    ap_account: str = Field(default="Accounts Payable", description="Accounts payable account name")
    expense_account: str = Field(default="Purchases", description="Default expense account name")
    tax_account: str = Field(default="Sales Tax", description="Tax account name")
    date_format: str = Field(default="%m/%d/%Y", description="Date format string")
    vendor_account_map: dict[str, str] = Field(
        default_factory=dict,
        description="Optional vendor name override to expense account mapping",
    )


def _resolve_amounts(inv: InvoiceRow) -> tuple[Decimal, Decimal, Decimal]:
    """Resolve total, tax, and net subtotal from invoice row."""
    total = Decimal(inv.total)
    tax = inv.tax_total or (
        (inv.cgst or Decimal("0.00"))
        + (inv.sgst or Decimal("0.00"))
        + (inv.igst or Decimal("0.00"))
    )
    subtotal = inv.subtotal if inv.subtotal is not None else (total - tax)
    if subtotal + tax != total:
        subtotal = total - tax
    return total, tax, subtotal


def export_quickbooks_iif(
    invoices: Sequence[InvoiceRow],
    output_path: Path,
    mapping: QuickBooksMappingConfig | None = None,
) -> Path:
    """Export invoices to QuickBooks IIF (Intuit Interchange Format) tab-delimited file."""
    cfg = mapping or QuickBooksMappingConfig()
    lines: list[str] = [
        "!TRNS\tTRNSID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO\tCLEAR\tTOPRINT",
        "!SPL\tSPLID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO\tCLEAR",
        "!ENDTRNS",
    ]
    for inv in invoices:
        vendor = inv.vendor_name
        docnum = inv.invoice_number or f"INV-{inv.id}"
        dt = inv.invoice_date.strftime(cfg.date_format) if inv.invoice_date else ""
        total, tax, subtotal = _resolve_amounts(inv)
        exp_acc = cfg.vendor_account_map.get(vendor, cfg.expense_account)

        lines.append(
            f"TRNS\t\tBILL\t{dt}\t{cfg.ap_account}\t{vendor}\t{-total:.2f}\t"
            f"{docnum}\tInvoice {docnum}\tN\tN"
        )
        lines.append(
            f"SPL\t\tBILL\t{dt}\t{exp_acc}\t{vendor}\t{subtotal:.2f}\t{docnum}\tExpense\tN"
        )
        if tax > 0:
            lines.append(
                f"SPL\t\tBILL\t{dt}\t{cfg.tax_account}\t{vendor}\t{tax:.2f}\t{docnum}\tTax\tN"
            )
        lines.append("ENDTRNS")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def export_quickbooks_csv(
    invoices: Sequence[InvoiceRow],
    output_path: Path,
    mapping: QuickBooksMappingConfig | None = None,
) -> Path:
    """Export invoices to QuickBooks standard bill import CSV file."""
    cfg = mapping or QuickBooksMappingConfig()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "Bill No",
        "Vendor",
        "Bill Date",
        "Due Date",
        "Terms",
        "Memo",
        "Expense Account",
        "Expense Amount",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for inv in invoices:
            vendor = inv.vendor_name
            docnum = inv.invoice_number or f"INV-{inv.id}"
            dt = inv.invoice_date.strftime(cfg.date_format) if inv.invoice_date else ""
            total, tax, subtotal = _resolve_amounts(inv)
            exp_acc = cfg.vendor_account_map.get(vendor, cfg.expense_account)

            if tax > 0 and subtotal > 0:
                writer.writerow(
                    [docnum, vendor, dt, "", "", f"Bill {docnum}", exp_acc, f"{subtotal:.2f}"]
                )
                writer.writerow(
                    [
                        docnum,
                        vendor,
                        dt,
                        "",
                        "",
                        f"Bill {docnum} Tax",
                        cfg.tax_account,
                        f"{tax:.2f}",
                    ]
                )
            else:
                writer.writerow(
                    [docnum, vendor, dt, "", "", f"Bill {docnum}", exp_acc, f"{total:.2f}"]
                )
    return output_path
