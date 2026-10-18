"""Monthly invoice data export generating multi-sheet Excel workbooks and CSV files."""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pandas as pd

from invoiceflow.db.tables import InvoiceRow


def prepare_export_dataframes(
    invoices: Sequence[InvoiceRow],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Transform a sequence of InvoiceRow objects into detailed and vendor summary DataFrames."""
    records = []
    for inv in invoices:
        records.append(
            {
                "Invoice ID": inv.id,
                "Date": inv.invoice_date.isoformat() if inv.invoice_date else "",
                "Vendor Name": inv.vendor_name,
                "Tax ID": inv.vendor_tax_id or "",
                "Invoice Number": inv.invoice_number or "",
                "Currency": inv.currency,
                "Subtotal": float(inv.subtotal) if inv.subtotal is not None else 0.0,
                "CGST": float(inv.cgst) if inv.cgst is not None else 0.0,
                "SGST": float(inv.sgst) if inv.sgst is not None else 0.0,
                "IGST": float(inv.igst) if inv.igst is not None else 0.0,
                "Tax Total": float(inv.tax_total) if inv.tax_total is not None else 0.0,
                "Total": float(inv.total),
                "Duplicate Of": inv.duplicate_of or "",
            }
        )

    columns = [
        "Invoice ID",
        "Date",
        "Vendor Name",
        "Tax ID",
        "Invoice Number",
        "Currency",
        "Subtotal",
        "CGST",
        "SGST",
        "IGST",
        "Tax Total",
        "Total",
        "Duplicate Of",
    ]
    df_invoices = pd.DataFrame(records, columns=columns)

    if not df_invoices.empty:
        df_summary = (
            df_invoices.groupby("Vendor Name", as_index=False)
            .agg(
                Invoice_Count=("Invoice ID", "count"),
                Subtotal=("Subtotal", "sum"),
                Tax_Total=("Tax Total", "sum"),
                Total=("Total", "sum"),
            )
            .rename(
                columns={
                    "Invoice_Count": "Invoice Count",
                    "Tax_Total": "Tax Total",
                }
            )
            .sort_values(by="Total", ascending=False)
        )
    else:
        summary_cols = ["Vendor Name", "Invoice Count", "Subtotal", "Tax Total", "Total"]
        df_summary = pd.DataFrame(columns=summary_cols)

    return df_invoices, df_summary


def export_to_excel(invoices: Sequence[InvoiceRow], output_path: Path | str) -> Path:
    """Generate an Excel workbook with 'Invoices' and 'Vendor Summary' sheets."""
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    df_invoices, df_summary = prepare_export_dataframes(invoices)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_invoices.to_excel(writer, sheet_name="Invoices", index=False)
        df_summary.to_excel(writer, sheet_name="Vendor Summary", index=False)

    return path


def export_to_csv(invoices: Sequence[InvoiceRow], output_path: Path | str) -> tuple[Path, Path]:
    """Generate CSV files for detailed invoices and vendor summary."""
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    df_invoices, df_summary = prepare_export_dataframes(invoices)

    inv_path = path if path.suffix.lower() == ".csv" else path.with_suffix(".csv")
    summary_path = inv_path.with_name(f"{inv_path.stem}_summary.csv")

    df_invoices.to_csv(inv_path, index=False)
    df_summary.to_csv(summary_path, index=False)
    return inv_path, summary_path


def export_monthly_data(
    invoices: Sequence[InvoiceRow],
    output_path: Path | str,
    export_format: Literal["xlsx", "csv"] = "xlsx",
) -> Path:
    """Export monthly invoices to the chosen format (xlsx or csv)."""
    if export_format == "xlsx":
        return export_to_excel(invoices, output_path)
    if export_format == "csv":
        inv_path, _ = export_to_csv(invoices, output_path)
        return inv_path
    raise ValueError(f"Unsupported export format '{export_format}' (expected 'xlsx' or 'csv')")
