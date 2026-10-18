"""Unit tests for Google Sheets export with mocked Google Sheets API."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from invoiceflow.db.tables import InvoiceRow
from invoiceflow.export.sheets import GoogleSheetsExporter


def _make_mock_invoice(inv_id: int, vendor: str, total: str) -> InvoiceRow:
    """Helper to create test InvoiceRow instances."""
    inv = InvoiceRow(
        document_id=inv_id,
        vendor_name=vendor,
        vendor_tax_id="27AAACR1234F1Z5",
        invoice_number=f"INV-{inv_id}",
        invoice_date=date(2024, 5, 10),
        currency="INR",
        subtotal=Decimal("1000.00"),
        cgst=Decimal("90.00"),
        sgst=Decimal("90.00"),
        igst=Decimal("0.00"),
        tax_total=Decimal("180.00"),
        total=Decimal(total),
        overall_confidence=0.95,
    )
    inv.id = inv_id
    return inv


def test_init_validation() -> None:
    """Verify initialization checks for spreadsheet ID and credentials."""
    with pytest.raises(ValueError, match="Spreadsheet ID must be provided"):
        GoogleSheetsExporter(spreadsheet_id="", service_account_file="creds.json")

    with pytest.raises(ValueError, match="Either service_account_file or service_account_info"):
        GoogleSheetsExporter(spreadsheet_id="sheet123")


def test_get_existing_invoice_ids() -> None:
    """Verify parsing of existing integer invoice IDs from spreadsheet column A."""
    exporter = GoogleSheetsExporter(
        spreadsheet_id="test_sheet_id",
        service_account_info={"type": "service_account"},
    )

    mock_service = MagicMock()
    mock_get_req = MagicMock()
    mock_get_req.execute.return_value = {
        "values": [["Invoice ID"], ["101"], [""], ["invalid"], ["102"]]
    }
    mock_service.spreadsheets().values().get.return_value = mock_get_req

    with patch.object(exporter, "get_service", return_value=mock_service):
        ids = exporter.get_existing_invoice_ids()

    assert ids == {101, 102}


def test_sync_invoices_first_time_appends_headers_and_data() -> None:
    """Verify empty sheet receives header row and new invoice rows."""
    exporter = GoogleSheetsExporter(
        spreadsheet_id="test_sheet_id",
        service_account_info={"type": "service_account"},
    )

    mock_service = MagicMock()

    # 1. ensure_headers check -> returns empty
    # 2. get_existing_invoice_ids check -> returns empty
    mock_get_headers = MagicMock()
    mock_get_headers.execute.return_value = {"values": []}

    mock_get_ids = MagicMock()
    mock_get_ids.execute.return_value = {"values": []}

    mock_service.spreadsheets().values().get.side_effect = [mock_get_headers, mock_get_ids]

    mock_append_req = MagicMock()
    mock_append_req.execute.return_value = {"updates": {"updatedRows": 2}}
    mock_service.spreadsheets().values().append.return_value = mock_append_req

    invoices = [
        _make_mock_invoice(1, "Vendor A", "1180.00"),
        _make_mock_invoice(2, "Vendor B", "2360.00"),
    ]

    with patch.object(exporter, "get_service", return_value=mock_service):
        count = exporter.sync_invoices(invoices)

    assert count == 2
    # Verify append was called twice: once for headers, once for invoice data
    assert mock_service.spreadsheets().values().append.call_count == 2


def test_sync_invoices_idempotency_prevents_duplicate_appends() -> None:
    """Verify that previously synced invoice IDs are ignored during sync."""
    exporter = GoogleSheetsExporter(
        spreadsheet_id="test_sheet_id",
        service_account_info={"type": "service_account"},
    )

    mock_service = MagicMock()

    mock_get_headers = MagicMock()
    mock_get_headers.execute.return_value = {"values": [["Invoice ID"]]}

    mock_get_ids = MagicMock()
    # Sheet already contains invoice ID 1
    mock_get_ids.execute.return_value = {"values": [["Invoice ID"], ["1"]]}

    mock_service.spreadsheets().values().get.side_effect = [mock_get_headers, mock_get_ids]

    mock_append_req = MagicMock()
    mock_append_req.execute.return_value = {"updates": {"updatedRows": 1}}
    mock_service.spreadsheets().values().append.return_value = mock_append_req

    invoices = [
        _make_mock_invoice(1, "Vendor A", "1180.00"),  # Already in sheet
        _make_mock_invoice(2, "Vendor B", "2360.00"),  # New invoice
    ]

    with patch.object(exporter, "get_service", return_value=mock_service):
        count = exporter.sync_invoices(invoices)

    assert count == 1
    # Only 1 append call (no header append needed, only 1 new row appended)
    assert mock_service.spreadsheets().values().append.call_count == 1

    # Verify the body passed to append contains only invoice ID 2
    _, kwargs = mock_service.spreadsheets().values().append.call_args
    assert len(kwargs["body"]["values"]) == 1
    assert kwargs["body"]["values"][0][0] == 2


def test_sync_invoices_all_already_synced_returns_zero() -> None:
    """Verify no API append calls are made when all invoices are already in the sheet."""
    exporter = GoogleSheetsExporter(
        spreadsheet_id="test_sheet_id",
        service_account_info={"type": "service_account"},
    )

    mock_service = MagicMock()
    mock_get_headers = MagicMock()
    mock_get_headers.execute.return_value = {"values": [["Invoice ID"]]}
    mock_get_ids = MagicMock()
    mock_get_ids.execute.return_value = {"values": [["Invoice ID"], ["1"], ["2"]]}
    mock_service.spreadsheets().values().get.side_effect = [mock_get_headers, mock_get_ids]

    invoices = [
        _make_mock_invoice(1, "Vendor A", "1180.00"),
        _make_mock_invoice(2, "Vendor B", "2360.00"),
    ]

    with patch.object(exporter, "get_service", return_value=mock_service):
        count = exporter.sync_invoices(invoices)

    assert count == 0
    assert mock_service.spreadsheets().values().append.call_count == 0


def test_sync_invoices_empty_list() -> None:
    """Verify syncing empty list returns 0 immediately without API calls."""
    exporter = GoogleSheetsExporter(
        spreadsheet_id="test_sheet_id",
        service_account_info={"type": "service_account"},
    )
    assert exporter.sync_invoices([]) == 0
