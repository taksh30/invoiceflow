"""Unit tests for field extraction engines and rules."""

from datetime import date
from decimal import Decimal

from invoiceflow.extract.fields import (
    CurrencyExtractor,
    InvoiceDateExtractor,
    InvoiceFieldsExtractor,
    InvoiceNumberExtractor,
    SubtotalExtractor,
    TaxExtractor,
    TotalExtractor,
    VendorNameExtractor,
    VendorTaxIdExtractor,
)
from invoiceflow.extract.text import TextResult


def test_total_extractor_anchored() -> None:
    extractor = TotalExtractor()
    text = "Subtotal: 1000.00\nTax: 180.00\nGrand Total: 1180.00"
    res = extractor.extract(text)
    assert res is not None
    assert res.value == Decimal("1180.00")
    assert res.confidence >= 0.8


def test_total_extractor_fallback() -> None:
    extractor = TotalExtractor()
    text = "Item A: 50.00\nItem B: 120.00\nMiscellaneous notes"
    res = extractor.extract(text)
    assert res is not None
    assert res.value == Decimal("120.00")
    assert res.confidence <= 0.5


def test_subtotal_extractor() -> None:
    extractor = SubtotalExtractor()
    text = "Subtotal: 2500.00\nTotal: 2975.00"
    res = extractor.extract(text)
    assert res is not None
    assert res.value == Decimal("2500.00")


def test_tax_extractor_with_gst_breakdown() -> None:
    extractor = TaxExtractor()
    text = "CGST: 90.00\nSGST: 90.00\nTotal: 1180.00"
    res = extractor.extract(text)
    assert res is not None
    breakdown = res.value
    assert breakdown["cgst"] == Decimal("90.00")
    assert breakdown["sgst"] == Decimal("90.00")
    assert breakdown["tax_total"] == Decimal("180.00")


def test_invoice_number_extractor() -> None:
    extractor = InvoiceNumberExtractor()
    text = "Company Ltd\nInvoice No: INV-2024-991\nDate: 01/05/2024"
    res = extractor.extract(text)
    assert res is not None
    assert res.value == "INV-2024-991"

    # OCR variation
    ocr_text = "Company Ltd\nInvoice Na: REC-8821\nTotal: 100"
    res_ocr = extractor.extract(ocr_text, is_ocr=True)
    assert res_ocr is not None
    assert res_ocr.value == "REC-8821"


def test_invoice_date_extractor() -> None:
    extractor = InvoiceDateExtractor()
    # IN locale: dd/mm/yyyy
    text_in = "Date: 15/05/2024\nTotal: 100"
    res_in = extractor.extract(text_in, locale="IN")
    assert res_in is not None
    assert res_in.value == date(2024, 5, 15)

    # US locale: mm/dd/yyyy
    text_us = "Date: 05/10/2024\nTotal: 100"
    res_us = extractor.extract(text_us, locale="US")
    assert res_us is not None
    assert res_us.value == date(2024, 5, 10)

    # EU locale: dd.mm.yyyy
    text_eu = "Dated: 10.05.2024\nTotal: 100"
    res_eu = extractor.extract(text_eu, locale="EU")
    assert res_eu is not None
    assert res_eu.value == date(2024, 5, 10)


def test_vendor_name_extractor() -> None:
    extractor = VendorNameExtractor()
    text = "Bharti Airtel Ltd\nTAX ID: 07AAACB2233N1Z8\nInvoice No: 123"
    res = extractor.extract(text)
    assert res is not None
    assert res.value == "Bharti Airtel Ltd"

    # Skips invoice/header words
    text_skip = "TAX INVOICE\nORIGINAL FOR RECIPIENT\nAcme Solutions\nTotal: 50"
    res_skip = extractor.extract(text_skip)
    assert res_skip is not None
    assert res_skip.value == "Acme Solutions"


def test_vendor_tax_id_extractor() -> None:
    extractor = VendorTaxIdExtractor()
    # Indian GSTIN
    text_in = "Vendor\nGSTIN: 27AAACR1234F1Z5\nTotal: 100"
    res_in = extractor.extract(text_in)
    assert res_in is not None
    assert res_in.value == "27AAACR1234F1Z5"

    # European VAT
    text_eu = "Vendor\nTAX ID: DE123456789\nTotal: 100"
    res_eu = extractor.extract(text_eu)
    assert res_eu is not None
    assert res_eu.value == "DE123456789"


def test_currency_extractor() -> None:
    extractor = CurrencyExtractor()
    assert extractor.extract("Total: ₹ 1,500.00").value == "INR"
    assert extractor.extract("Total: $120.00").value == "USD"
    assert extractor.extract("Total: 500,00 €").value == "EUR"
    assert extractor.extract("Total: 100.00", locale="US").value == "USD"


def test_invoice_fields_extractor_pipeline() -> None:
    extractor = InvoiceFieldsExtractor()
    sample_text = (
        "Acme Cloud Services\n"
        "GSTIN: 29AAACI4567M1ZV\n"
        "Invoice No: ACM-1002\n"
        "Date: 20/05/2024\n"
        "Currency: INR\n"
        "Subtotal: 1000.00\n"
        "Tax: 180.00\n"
        "Grand Total: 1180.00"
    )
    text_result = TextResult(
        raw_text=sample_text,
        pages=[sample_text],
        words=[],
        method="pdfplumber",
    )
    invoice = extractor.extract_fields(text_result, locale="IN")
    assert invoice.vendor_name == "Acme Cloud Services"
    assert invoice.vendor_tax_id == "29AAACI4567M1ZV"
    assert invoice.invoice_number == "ACM-1002"
    assert invoice.invoice_date == date(2024, 5, 20)
    assert invoice.currency == "INR"
    assert invoice.subtotal == Decimal("1000.00")
    assert invoice.tax_total == Decimal("180.00")
    assert invoice.total == Decimal("1180.00")
    assert invoice.overall_confidence >= 0.85
