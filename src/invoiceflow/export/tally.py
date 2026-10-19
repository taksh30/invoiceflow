"""Tally ERP/Prime XML purchase voucher export generator."""

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from invoiceflow.db.tables import InvoiceRow


class TallyMappingConfig(BaseModel):
    """Configuration mapping for Tally XML purchase voucher generation."""

    voucher_type: str = Field(default="Purchase", description="Tally voucher type")
    purchase_ledger: str = Field(
        default="Purchase Account", description="Default purchase/expense ledger"
    )
    cgst_ledger: str = Field(default="Input CGST", description="CGST tax ledger")
    sgst_ledger: str = Field(default="Input SGST", description="SGST tax ledger")
    igst_ledger: str = Field(default="Input IGST", description="IGST tax ledger")
    tax_ledger: str = Field(default="Input Tax", description="Generic tax ledger when unsegmented")
    company_name: str = Field(default="Default Company", description="Target company name")
    vendor_ledger_map: dict[str, str] = Field(
        default_factory=dict,
        description="Optional vendor name override to ledger name mapping",
    )


def _append_ledger_entry(
    parent: ET.Element, ledger_name: str, is_deemed_positive: str, amount: Decimal
) -> None:
    """Append an ALLLEDGERENTRIES.LIST element to a voucher element."""
    entry = ET.SubElement(parent, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(entry, "LEDGERNAME").text = ledger_name
    ET.SubElement(entry, "ISDEEMEDPOSITIVE").text = is_deemed_positive
    ET.SubElement(entry, "AMOUNT").text = f"{amount:.2f}"


def _append_tax_entries(
    voucher: ET.Element, inv: InvoiceRow, mapping: TallyMappingConfig
) -> Decimal:
    """Append tax ledger entries and return total allocated tax amount."""
    cgst = inv.cgst or Decimal("0.00")
    sgst = inv.sgst or Decimal("0.00")
    igst = inv.igst or Decimal("0.00")
    allocated = Decimal("0.00")

    if cgst > 0:
        _append_ledger_entry(voucher, mapping.cgst_ledger, "Yes", -cgst)
        allocated += cgst
    if sgst > 0:
        _append_ledger_entry(voucher, mapping.sgst_ledger, "Yes", -sgst)
        allocated += sgst
    if igst > 0:
        _append_ledger_entry(voucher, mapping.igst_ledger, "Yes", -igst)
        allocated += igst

    if allocated == 0 and inv.tax_total and inv.tax_total > 0:
        _append_ledger_entry(voucher, mapping.tax_ledger, "Yes", -inv.tax_total)
        allocated += inv.tax_total
    return allocated


def build_tally_voucher_element(inv: InvoiceRow, mapping: TallyMappingConfig) -> ET.Element:
    """Build an individual XML VOUCHER element from an InvoiceRow."""
    msg = ET.Element("TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
    voucher = ET.SubElement(msg, "VOUCHER", {"VCHTYPE": mapping.voucher_type, "ACTION": "Create"})

    v_date = (
        inv.invoice_date.strftime("%Y%m%d")
        if inv.invoice_date
        else datetime.now(UTC).strftime("%Y%m%d")
    )
    doc_num = inv.invoice_number or f"INV-{inv.id}"
    party = mapping.vendor_ledger_map.get(inv.vendor_name, inv.vendor_name)

    ET.SubElement(voucher, "DATE").text = v_date
    ET.SubElement(voucher, "VOUCHERTYPENAME").text = mapping.voucher_type
    ET.SubElement(voucher, "REFERENCE").text = doc_num
    ET.SubElement(voucher, "PARTYLEDGERNAME").text = party
    ET.SubElement(voucher, "PERSISTEDVIEW").text = "Invoice Voucher View"

    total = Decimal(inv.total)
    _append_ledger_entry(voucher, party, "No", total)
    allocated_tax = _append_tax_entries(voucher, inv, mapping)
    purchase_amt = total - allocated_tax
    _append_ledger_entry(voucher, mapping.purchase_ledger, "Yes", -purchase_amt)

    return msg


def build_tally_xml(
    invoices: Sequence[InvoiceRow], mapping: TallyMappingConfig | None = None
) -> str:
    """Build a complete, formatted Tally XML import envelope string."""
    cfg = mapping or TallyMappingConfig()
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    req_desc = ET.SubElement(import_data, "REQUESTDESC")
    ET.SubElement(req_desc, "REPORTNAME").text = "Vouchers"
    static_vars = ET.SubElement(req_desc, "STATICVARIABLES")
    ET.SubElement(static_vars, "SVCURRENTCOMPANY").text = cfg.company_name

    req_data = ET.SubElement(import_data, "REQUESTDATA")
    for inv in invoices:
        req_data.append(build_tally_voucher_element(inv, cfg))

    ET.indent(envelope, space="  ")
    xml_bytes = ET.tostring(envelope, encoding="utf-8", xml_declaration=True)
    return str(xml_bytes.decode("utf-8"))


def export_tally_xml(
    invoices: Sequence[InvoiceRow],
    output_path: Path,
    mapping: TallyMappingConfig | None = None,
) -> Path:
    """Export invoices to a Tally XML envelope file."""
    xml_content = build_tally_xml(invoices, mapping=mapping)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content, encoding="utf-8")
    return output_path
