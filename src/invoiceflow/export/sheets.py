"""Google Sheets export syncing invoices via Service Account credentials idempotently."""

import socket
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from invoiceflow.db.tables import InvoiceRow
from invoiceflow.errors import InvoiceFlowError
from invoiceflow.utils.logging import get_logger

logger = get_logger("export.sheets")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_HEADERS = [
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
TRANSIENT_API_ERRORS = (
    OSError,
    socket.error,
    TimeoutError,
    ConnectionError,
    HttpError,
)


@retry(
    retry=retry_if_exception_type(TRANSIENT_API_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _execute_with_retry(request: Any) -> Any:
    """Execute a Google API request with tenacity retries on transient errors."""
    return request.execute()


class GoogleSheetsExporter:
    """Synchronizes invoice records with a Google Spreadsheet using service account credentials."""

    def __init__(
        self,
        spreadsheet_id: str,
        service_account_file: Path | str | None = None,
        service_account_info: dict[str, Any] | None = None,
        sheet_name: str = "Invoices",
    ) -> None:
        """Initialize Google Sheets exporter with credentials and target sheet."""
        if not spreadsheet_id:
            raise ValueError("Spreadsheet ID must be provided")
        if not service_account_file and not service_account_info:
            raise ValueError("Either service_account_file or service_account_info must be provided")

        self.spreadsheet_id = spreadsheet_id
        self.service_account_file = Path(service_account_file) if service_account_file else None
        self.service_account_info = service_account_info
        self.sheet_name = sheet_name
        self._service: Resource | None = None

    def get_service(self) -> Resource:
        """Initialize and cache the Google Sheets API client Resource."""
        if self._service is not None:
            return self._service

        try:
            if self.service_account_file:
                creds = service_account.Credentials.from_service_account_file(
                    str(self.service_account_file), scopes=SCOPES
                )
            else:
                creds = service_account.Credentials.from_service_account_info(
                    self.service_account_info, scopes=SCOPES
                )
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            return self._service
        except Exception as err:
            raise InvoiceFlowError(f"Failed to authenticate Google Sheets service: {err}") from err

    def get_existing_invoice_ids(self) -> set[int]:
        """Fetch column A from Google Sheet to find all previously appended invoice IDs."""
        service = self.get_service()
        req = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:A",
            )
        )
        res = _execute_with_retry(req)
        rows = res.get("values", [])

        existing_ids: set[int] = set()
        for row in rows:
            if row and str(row[0]).strip().isdigit():
                existing_ids.add(int(row[0]))
        return existing_ids

    def _ensure_headers(self) -> None:
        """Add column headers if sheet is empty."""
        service = self.get_service()
        req = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1:Z1",
            )
        )
        res = _execute_with_retry(req)
        if not res.get("values"):
            append_req = (
                service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [SHEET_HEADERS]},
                )
            )
            _execute_with_retry(append_req)

    def _format_row(self, inv: InvoiceRow) -> list[Any]:
        """Format an InvoiceRow instance as a list of spreadsheet cell values."""
        return [
            inv.id,
            inv.invoice_date.isoformat() if inv.invoice_date else "",
            inv.vendor_name,
            inv.vendor_tax_id or "",
            inv.invoice_number or "",
            inv.currency,
            float(inv.subtotal) if inv.subtotal is not None else 0.0,
            float(inv.cgst) if inv.cgst is not None else 0.0,
            float(inv.sgst) if inv.sgst is not None else 0.0,
            float(inv.igst) if inv.igst is not None else 0.0,
            float(inv.tax_total) if inv.tax_total is not None else 0.0,
            float(inv.total),
            str(inv.duplicate_of) if inv.duplicate_of else "",
        ]

    def sync_invoices(self, invoices: Sequence[InvoiceRow]) -> int:
        """Append unseen invoices to Google Sheets, ensuring idempotency by invoice ID."""
        if not invoices:
            return 0

        self._ensure_headers()
        existing_ids = self.get_existing_invoice_ids()

        new_invoices = [inv for inv in invoices if inv.id not in existing_ids]
        if not new_invoices:
            logger.info(
                "All invoices already synced to Google Sheet", extra={"count": len(invoices)}
            )
            return 0

        rows = [self._format_row(inv) for inv in new_invoices]
        service = self.get_service()
        req = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": rows},
            )
        )
        _execute_with_retry(req)

        logger.info("Appended new invoices to Google Sheet", extra={"count": len(rows)})
        return len(rows)
