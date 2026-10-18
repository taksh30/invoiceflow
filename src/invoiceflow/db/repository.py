"""Repository pattern for database operations on documents, invoices, and audit logs."""

import calendar
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from invoiceflow.db.tables import DocumentRow, InvoiceRow, ProcessingEventRow
from invoiceflow.models import ExtractedInvoice


class InvoiceRepository:
    """Encapsulates persistence and query operations for InvoiceFlow."""

    def __init__(self, session: Session) -> None:
        """Initialize repository with an active SQLAlchemy session."""
        self.session = session

    def add_document(
        self,
        file_sha256: str,
        original_name: str,
        stored_path: str,
        source: str,
        source_ref: str,
        doc_type: str,
        status: str = "processed",
        error: str | None = None,
    ) -> DocumentRow:
        """Persist a new document row."""
        doc = DocumentRow(
            file_sha256=file_sha256,
            original_name=original_name,
            stored_path=stored_path,
            source=source,
            source_ref=source_ref,
            doc_type=doc_type,
            status=status,
            error=error,
        )
        self.session.add(doc)
        self.session.flush()
        return doc

    def get_by_hash(self, sha256: str) -> DocumentRow | None:
        """Find a document by its unique SHA-256 content hash."""
        stmt = select(DocumentRow).where(DocumentRow.file_sha256 == sha256)
        return self.session.scalars(stmt).first()

    def add_invoice(
        self,
        document_id: int,
        invoice: ExtractedInvoice,
        duplicate_of: int | None = None,
    ) -> InvoiceRow:
        """Persist an extracted invoice record associated with a document."""
        row = InvoiceRow(
            document_id=document_id,
            vendor_name=invoice.vendor_name,
            vendor_tax_id=invoice.vendor_tax_id,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            currency=invoice.currency,
            subtotal=invoice.subtotal,
            tax_total=invoice.tax_total,
            cgst=invoice.cgst,
            sgst=invoice.sgst,
            igst=invoice.igst,
            total=invoice.total,
            confidence=invoice.confidence,
            overall_confidence=invoice.overall_confidence,
            duplicate_of=duplicate_of,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def find_candidates(
        self,
        vendor_name: str | None = None,
        invoice_number: str | None = None,
        total: Decimal | None = None,
        invoice_date: date | None = None,
    ) -> Sequence[InvoiceRow]:
        """Find candidate invoices matching invoice number or vendor + total/date."""
        conditions = []
        if invoice_number and invoice_number.strip():
            conditions.append(InvoiceRow.invoice_number == invoice_number.strip())

        if vendor_name and total is not None:
            v_match = func.lower(InvoiceRow.vendor_name) == vendor_name.strip().lower()
            t_match = InvoiceRow.total == total
            if invoice_date:
                conditions.append(and_(v_match, t_match, InvoiceRow.invoice_date == invoice_date))
            else:
                conditions.append(and_(v_match, t_match))

        if not conditions:
            return []

        stmt = select(InvoiceRow).where(or_(*conditions))
        return self.session.scalars(stmt).all()

    def list_by_month(self, year: int, month: int) -> Sequence[InvoiceRow]:
        """List invoices for a given calendar month ordered by invoice date."""
        _, last_day = calendar.monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        stmt = (
            select(InvoiceRow)
            .where(
                and_(
                    InvoiceRow.invoice_date >= start_date,
                    InvoiceRow.invoice_date <= end_date,
                )
            )
            .order_by(InvoiceRow.invoice_date.asc())
        )
        return self.session.scalars(stmt).all()

    def log_event(
        self,
        document_id: int,
        stage: str,
        message: str,
        level: str = "INFO",
    ) -> ProcessingEventRow:
        """Create an audit event entry."""
        event = ProcessingEventRow(
            document_id=document_id,
            stage=stage,
            level=level,
            message=message,
        )
        self.session.add(event)
        self.session.flush()
        return event
