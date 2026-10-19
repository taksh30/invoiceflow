"""FastAPI web application for human invoice review and training data collection."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Form, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from invoiceflow.config import Settings
from invoiceflow.db.base import create_db_engine, get_session_factory, init_db
from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.models import ExtractedInvoice
from invoiceflow.ui.corrections import CorrectionRecord, save_correction
from invoiceflow.ui.templates import (
    render_review_queue_page,
    render_review_workspace,
    render_save_success_toast,
)
from invoiceflow.utils.money import parse_money


def _parse_optional_decimal(raw: str | None) -> Decimal | None:
    """Safely parse optional decimal string into Decimal."""
    if not raw or not raw.strip():
        return None
    try:
        return parse_money(raw.strip())
    except (ValueError, TypeError):
        return None


def _parse_optional_date(raw: str | None) -> date | None:
    """Safely parse optional date string into date object."""
    if not raw or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, TypeError):
        return None


def _detect_media_type(filename: str) -> str:
    """Return appropriate MIME media type from document file extension."""
    low = filename.lower()
    if low.endswith(".pdf"):
        return "application/pdf"
    if low.endswith(".png"):
        return "image/png"
    if low.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    return "application/octet-stream"


def create_ui_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Construct and configure the FastAPI review station application."""
    active_settings = settings or Settings()
    active_settings.ensure_directories()
    active_engine = engine or create_db_engine(active_settings.database_url)
    init_db(active_engine)
    session_factory = get_session_factory(active_engine)

    app = FastAPI(
        title="InvoiceFlow Review Station",
        description="FastAPI + HTMX review interface for low-confidence invoices.",
        version="0.1.0",
    )

    def get_repo() -> Generator[InvoiceRepository, None, None]:
        """Dependency yielding active repository session."""
        session: Session = session_factory()
        repo = InvoiceRepository(session)
        try:
            yield repo
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @app.get("/", response_class=HTMLResponse)
    def review_queue(repo: Annotated[InvoiceRepository, Depends(get_repo)]) -> HTMLResponse:
        """List all documents currently requiring human review."""
        documents = repo.list_documents(status="needs_review")
        items = [(doc, repo.get_invoice_by_document_id(doc.id)) for doc in documents]
        return HTMLResponse(render_review_queue_page(items))

    @app.get("/review/{doc_id}", response_class=HTMLResponse)
    def review_document(
        doc_id: int,
        repo: Annotated[InvoiceRepository, Depends(get_repo)],
    ) -> HTMLResponse:
        """Render side-by-side document preview and editable field form."""
        doc = repo.get_document_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        inv = repo.get_invoice_by_document_id(doc_id)
        raw_url = f"/document/{doc_id}/file"
        return HTMLResponse(render_review_workspace(doc, inv, raw_url=raw_url))

    @app.get("/document/{doc_id}/file")
    def stream_document_file(
        doc_id: int,
        repo: Annotated[InvoiceRepository, Depends(get_repo)],
    ) -> FileResponse:
        """Stream raw PDF or image file bytes for inline document rendering."""
        doc = repo.get_document_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        file_path = Path(doc.stored_path)
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Stored file missing on disk"
            )
        media_type = _detect_media_type(doc.original_name)
        return FileResponse(file_path, media_type=media_type)

    @app.post("/review/{doc_id}/save", response_class=HTMLResponse)
    def save_correction_endpoint(
        doc_id: int,
        repo: Annotated[InvoiceRepository, Depends(get_repo)],
        vendor_name: Annotated[str, Form()],
        total: Annotated[str, Form()],
        vendor_tax_id: Annotated[str | None, Form()] = None,
        invoice_number: Annotated[str | None, Form()] = None,
        invoice_date: Annotated[str | None, Form()] = None,
        currency: Annotated[str, Form()] = "INR",
        subtotal: Annotated[str | None, Form()] = None,
        tax_total: Annotated[str | None, Form()] = None,
        cgst: Annotated[str | None, Form()] = None,
        sgst: Annotated[str | None, Form()] = None,
        igst: Annotated[str | None, Form()] = None,
        save_as_rule: Annotated[bool, Form()] = False,
    ) -> HTMLResponse:
        """Save reviewer corrections, promote document status, and store training example."""
        doc = repo.get_document_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        inv_before = repo.get_invoice_by_document_id(doc_id)
        before_dict: dict[str, Any] = {}
        if inv_before:
            before_dict = {
                "vendor_name": inv_before.vendor_name,
                "invoice_number": inv_before.invoice_number,
                "total": str(inv_before.total),
                "confidence": inv_before.confidence,
            }

        total_dec = _parse_optional_decimal(total) or Decimal("0.01")
        corrected_inv = ExtractedInvoice(
            vendor_name=vendor_name.strip(),
            vendor_tax_id=vendor_tax_id.strip() if vendor_tax_id else None,
            invoice_number=invoice_number.strip() if invoice_number else None,
            invoice_date=_parse_optional_date(invoice_date),
            currency=currency.strip().upper(),
            subtotal=_parse_optional_decimal(subtotal),
            tax_total=_parse_optional_decimal(tax_total),
            cgst=_parse_optional_decimal(cgst),
            sgst=_parse_optional_decimal(sgst),
            igst=_parse_optional_decimal(igst),
            total=total_dec,
            confidence={"manual_review": 1.0},
            overall_confidence=1.0,
        )

        repo.update_invoice(doc_id, corrected_inv)
        repo.update_document_status(doc_id, "processed", error=None)
        repo.log_event(
            doc_id,
            "review_ui",
            f"Review correction: vendor='{corrected_inv.vendor_name}', total={corrected_inv.total}",
        )

        if save_as_rule:
            record = CorrectionRecord(
                document_id=doc_id,
                original_name=doc.original_name,
                file_sha256=doc.file_sha256,
                original_fields=before_dict,
                corrected_fields=corrected_inv.model_dump(mode="json"),
                save_as_rule=True,
            )
            save_correction(active_settings.corrections_dir, record)

        return HTMLResponse(render_save_success_toast(doc_id))

    return app
