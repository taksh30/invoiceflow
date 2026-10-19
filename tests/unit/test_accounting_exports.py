"""Unit tests for Tally XML and QuickBooks accounting exports."""

import csv
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoiceflow.db.tables import InvoiceRow
from invoiceflow.export.quickbooks import (
    QuickBooksMappingConfig,
    export_quickbooks_csv,
    export_quickbooks_iif,
)
from invoiceflow.export.tally import (
    TallyMappingConfig,
    build_tally_xml,
    export_tally_xml,
)


def _make_invoice(
    inv_id: int,
    vendor_name: str = "Acme Corp",
    total: str = "1180.00",
    subtotal: str = "1000.00",
    cgst: str = "90.00",
    sgst: str = "90.00",
    igst: str = "0.00",
    tax_total: str = "180.00",
    invoice_date: date | None = date(2024, 5, 15),
    invoice_number: str = "INV-2024-001",
) -> InvoiceRow:
    """Helper to instantiate mock InvoiceRow for testing accounting exports."""
    inv = InvoiceRow(
        document_id=inv_id,
        vendor_name=vendor_name,
        vendor_tax_id="27AAACR1234F1Z5",
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        currency="INR",
        subtotal=Decimal(subtotal),
        cgst=Decimal(cgst),
        sgst=Decimal(sgst),
        igst=Decimal(igst),
        tax_total=Decimal(tax_total),
        total=Decimal(total),
        overall_confidence=0.95,
    )
    inv.id = inv_id
    return inv


def test_tally_xml_structure_and_balance(tmp_path: Path) -> None:
    """Verify Tally XML is well-formed, contains purchase vouchers, and debits/credits balance."""
    inv = _make_invoice(1, total="1180.00", subtotal="1000.00", cgst="90.00", sgst="90.00")
    dest = tmp_path / "tally_export.xml"
    res_path = export_tally_xml([inv], dest)
    assert res_path.exists()

    tree = ET.parse(res_path)
    root = tree.getroot()
    assert root.tag == "ENVELOPE"

    tally_req = root.find(".//HEADER/TALLYREQUEST")
    assert tally_req is not None and tally_req.text == "Import Data"

    voucher = root.find(".//BODY/IMPORTDATA/REQUESTDATA/TALLYMESSAGE/VOUCHER")
    assert voucher is not None
    assert voucher.attrib["VCHTYPE"] == "Purchase"
    assert voucher.findtext("REFERENCE") == "INV-2024-001"
    assert voucher.findtext("PARTYLEDGERNAME") == "Acme Corp"
    assert voucher.findtext("DATE") == "20240515"

    entries = voucher.findall("ALLLEDGERENTRIES.LIST")
    assert len(entries) >= 3  # Party, Purchase, CGST, SGST

    balance = Decimal("0.00")
    for entry in entries:
        amt = Decimal(entry.findtext("AMOUNT", "0.00"))
        balance += amt

    # Sum of positive credit + negative debits in Tally convention must equal exactly zero
    assert balance == Decimal("0.00")


def test_tally_xml_custom_mapping_and_igst(tmp_path: Path) -> None:
    """Verify custom mapping config overrides ledger names and handles IGST."""
    inv = _make_invoice(
        2,
        vendor_name="TechSupplies Ltd",
        total="5900.00",
        subtotal="5000.00",
        cgst="0.00",
        sgst="0.00",
        igst="900.00",
        tax_total="900.00",
        invoice_date=date(2024, 6, 20),
    )
    mapping = TallyMappingConfig(
        voucher_type="Purchase Order",
        purchase_ledger="Cost of Goods Sold",
        igst_ledger="Custom Input IGST",
        company_name="Enterprise Ltd",
        vendor_ledger_map={"TechSupplies Ltd": "TechSupplies Creditor"},
    )
    xml_str = build_tally_xml([inv], mapping=mapping)
    root = ET.fromstring(xml_str)

    assert root.findtext(".//STATICVARIABLES/SVCURRENTCOMPANY") == "Enterprise Ltd"
    voucher = root.find(".//VOUCHER")
    assert voucher is not None
    assert voucher.attrib["VCHTYPE"] == "Purchase Order"
    assert voucher.findtext("PARTYLEDGERNAME") == "TechSupplies Creditor"

    ledger_names = [e.findtext("LEDGERNAME") for e in voucher.findall("ALLLEDGERENTRIES.LIST")]
    assert "TechSupplies Creditor" in ledger_names
    assert "Cost of Goods Sold" in ledger_names
    assert "Custom Input IGST" in ledger_names


def test_quickbooks_iif_structure_and_balance(tmp_path: Path) -> None:
    """Verify QuickBooks IIF tab-delimited format and balanced entries."""
    inv = _make_invoice(3, total="1180.00", subtotal="1000.00", cgst="90.00", sgst="90.00")
    out_file = tmp_path / "qb_export.iif"
    res_path = export_quickbooks_iif([inv], out_file)
    assert res_path.exists()

    content = res_path.read_text(encoding="utf-8")
    lines = [line.strip().split("\t") for line in content.splitlines() if line.strip()]

    assert lines[0][0] == "!TRNS"
    assert lines[1][0] == "!SPL"
    assert lines[2][0] == "!ENDTRNS"

    trns_row = next(r for r in lines if r[0] == "TRNS")
    spl_rows = [r for r in lines if r[0] == "SPL"]

    # TRNS amount is negative (-1180.00)
    trns_amount = Decimal(trns_row[6])
    assert trns_amount == Decimal("-1180.00")
    assert trns_row[4] == "Accounts Payable"
    assert trns_row[5] == "Acme Corp"

    # Sum of TRNS and SPL amounts must balance to 0.00
    spl_sum = sum(Decimal(r[6]) for r in spl_rows)
    assert trns_amount + spl_sum == Decimal("0.00")


def test_quickbooks_csv_export(tmp_path: Path) -> None:
    """Verify QuickBooks CSV export schema and content."""
    inv = _make_invoice(
        4,
        vendor_name="Global Logistics",
        total="2360.00",
        subtotal="2000.00",
        tax_total="360.00",
        invoice_date=date(2024, 7, 10),
    )
    mapping = QuickBooksMappingConfig(
        expense_account="Freight & Shipping",
        vendor_account_map={"Global Logistics": "Logistics Outsource"},
    )
    out_file = tmp_path / "qb_bills.csv"
    export_quickbooks_csv([inv], out_file, mapping=mapping)

    with out_file.open(newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert reader[0] == [
        "Bill No",
        "Vendor",
        "Bill Date",
        "Due Date",
        "Terms",
        "Memo",
        "Expense Account",
        "Expense Amount",
    ]
    # Two split rows: Expense + Tax
    assert len(reader) == 3
    assert reader[1][0] == "INV-2024-001"
    assert reader[1][1] == "Global Logistics"
    assert reader[1][2] == "07/10/2024"
    assert reader[1][6] == "Logistics Outsource"
    assert reader[1][7] == "2000.00"

    assert reader[2][6] == "Sales Tax"
    assert reader[2][7] == "360.00"


def test_accounting_exports_empty(tmp_path: Path) -> None:
    """Verify exporters handle empty invoice sequences cleanly."""
    xml_path = export_tally_xml([], tmp_path / "empty.xml")
    assert xml_path.exists()
    root = ET.parse(xml_path).getroot()
    assert len(root.findall(".//VOUCHER")) == 0

    iif_path = export_quickbooks_iif([], tmp_path / "empty.iif")
    assert iif_path.exists()
    iif_lines = iif_path.read_text(encoding="utf-8").splitlines()
    assert len(iif_lines) == 3  # Header rows only

    csv_path = export_quickbooks_csv([], tmp_path / "empty.csv")
    assert csv_path.exists()
    csv_lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) == 1  # Header row only
