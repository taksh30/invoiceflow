"""Pipeline orchestrator executing end-to-end processing with per-document error isolation."""

import hashlib
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.db.tables import DocumentRow, InvoiceRow
from invoiceflow.dedupe import find_duplicate
from invoiceflow.extract.classify import classify_document
from invoiceflow.extract.fields import InvoiceFieldsExtractor
from invoiceflow.extract.text import extract_text
from invoiceflow.models import (
    DocumentSource,
    DocumentType,
    ExtractedInvoice,
    ProcessingStatus,
    RawDocument,
)
from invoiceflow.sources.folder import FolderSource
from invoiceflow.validate import validate_invoice


class PipelineResult(BaseModel):
    """Outcome of processing an individual document through the pipeline."""

    document: DocumentRow
    invoice: InvoiceRow | None = None
    status: ProcessingStatus
    is_duplicate: bool = False
    error: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class Pipeline:
    """Coordinates ingest, text extraction, field extraction, validation, and deduplication."""

    def __init__(
        self,
        session: Session,
        raw_storage_dir: Path | str = "data/raw",
        default_locale: str = "IN",
    ) -> None:
        """Initialize pipeline with database session and configuration."""
        self.session = session
        self.repo = InvoiceRepository(session)
        self.raw_storage_dir = Path(raw_storage_dir)
        self.raw_storage_dir.mkdir(parents=True, exist_ok=True)
        self.extractor = InvoiceFieldsExtractor()
        self.default_locale = default_locale

    def _detect_locale(self, filename: str) -> str:
        """Infer country locale from filename heuristic or fallback to default."""
        low = filename.lower()
        if "_us_" in low:
            return "US"
        if "_eu_" in low:
            return "EU"
        return self.default_locale

    def _save_raw_file(self, content: bytes, filename: str, sha256: str) -> Path:
        """Persist raw file bytes to storage directory keyed by SHA-256."""
        ext = Path(filename).suffix.lower()
        dest_path = self.raw_storage_dir / f"{sha256}{ext}"
        dest_path.write_bytes(content)
        return dest_path

    def _dedupe_and_persist(
        self,
        doc_id: int,
        invoice: ExtractedInvoice,
        val_status: ProcessingStatus,
        val_reasons: list[str],
    ) -> tuple[ProcessingStatus, bool, InvoiceRow]:
        """Perform duplicate check and persist final invoice record."""
        is_dup = False
        dup_of_id = None

        if val_status == ProcessingStatus.PROCESSED:
            dedup_res = find_duplicate(invoice, self.repo)
            if dedup_res.is_duplicate:
                is_dup = True
                dup_of_id = dedup_res.duplicate_of_id
                final_status = ProcessingStatus.DUPLICATE
                self.repo.log_event(doc_id, "dedupe", dedup_res.reason or "Duplicate detected")
            else:
                final_status = ProcessingStatus.PROCESSED
                self.repo.log_event(doc_id, "dedupe", "No duplicate found")
        else:
            final_status = val_status

        error_msg = "; ".join(val_reasons) if val_reasons else None
        self.repo.update_document_status(doc_id, final_status.value, error=error_msg)
        inv_row = self.repo.add_invoice(doc_id, invoice, duplicate_of=dup_of_id)
        self.repo.log_event(
            doc_id, "persist", f"Persisted invoice with status={final_status.value}"
        )
        self.session.commit()
        return final_status, is_dup, inv_row

    def _process_pipeline_stages(self, doc: DocumentRow, stored_path: Path) -> PipelineResult:
        """Execute extraction, validation, and deduplication with per-document error isolation."""
        try:
            locale = self._detect_locale(doc.original_name)

            text_res = extract_text(stored_path)
            self.repo.log_event(doc.id, "extract_text", f"Extracted text via {text_res.method}")

            extracted_inv = self.extractor.extract_fields(text_res, locale=locale)
            self.repo.log_event(
                doc.id,
                "extract_fields",
                f"Extracted vendor='{extracted_inv.vendor_name}', total={extracted_inv.total}",
            )

            val_res = validate_invoice(extracted_inv)
            self.repo.log_event(doc.id, "validate", f"Validation status={val_res.status.value}")

            final_status, is_dup, inv_row = self._dedupe_and_persist(
                doc.id, val_res.invoice, val_res.status, val_res.reasons
            )
            err_msg = "; ".join(val_res.reasons) if val_res.reasons else None

            return PipelineResult(
                document=doc,
                invoice=inv_row,
                status=final_status,
                is_duplicate=is_dup,
                error=err_msg,
            )
        except Exception as exc:
            self.session.rollback()
            self.repo.update_document_status(doc.id, ProcessingStatus.FAILED.value, error=str(exc))
            self.repo.log_event(doc.id, "pipeline", f"Pipeline error: {exc}", level="ERROR")
            self.session.commit()
            return PipelineResult(
                document=doc,
                invoice=None,
                status=ProcessingStatus.FAILED,
                error=str(exc),
            )

    def process_raw_document(self, raw_doc: RawDocument) -> PipelineResult:
        """Ingest, isolate errors, and execute full processing pipeline on a RawDocument."""
        sha256 = hashlib.sha256(raw_doc.content).hexdigest()
        existing = self.repo.get_by_hash(sha256)

        if existing:
            self.repo.log_event(
                existing.id, "ingest", f"Document with hash {sha256[:8]} already ingested"
            )
            self.session.commit()
            inv = self.repo.get_invoice_by_document_id(existing.id)
            return PipelineResult(
                document=existing,
                invoice=inv,
                status=ProcessingStatus(existing.status),
                is_duplicate=True,
            )

        stored_path = self._save_raw_file(raw_doc.content, raw_doc.filename, sha256)

        try:
            doc_type = classify_document(raw_doc.content, raw_doc.filename)
            doc_type_str = doc_type.value
            classify_error = None
        except Exception as exc:
            doc_type_str = DocumentType.SCANNED_PDF.value
            classify_error = str(exc)

        doc = self.repo.add_document(
            file_sha256=sha256,
            original_name=raw_doc.filename,
            stored_path=str(stored_path),
            source=raw_doc.source.value,
            source_ref=raw_doc.source_ref,
            doc_type=doc_type_str,
            status="failed" if classify_error else "processing",
            error=classify_error,
        )
        self.repo.log_event(doc.id, "ingest", f"Ingested {raw_doc.filename}")

        if classify_error:
            self.repo.log_event(
                doc.id, "classify", f"Classification failed: {classify_error}", level="ERROR"
            )
            self.session.commit()
            return PipelineResult(
                document=doc,
                invoice=None,
                status=ProcessingStatus.FAILED,
                error=classify_error,
            )

        self.repo.log_event(doc.id, "classify", f"Classified as {doc_type_str}")
        self.session.commit()

        return self._process_pipeline_stages(doc, stored_path)

    def process_file(self, file_path: Path | str, source_ref: str | None = None) -> PipelineResult:
        """Process a single file from disk through the pipeline."""
        path = Path(file_path).resolve()
        content = path.read_bytes()
        raw_doc = RawDocument(
            content=content,
            filename=path.name,
            source=DocumentSource.FOLDER,
            source_ref=source_ref or str(path),
        )
        return self.process_raw_document(raw_doc)

    def process_folder(self, folder_path: Path | str) -> list[PipelineResult]:
        """Scan and process all supported documents in a folder."""
        source = FolderSource(Path(folder_path))
        raw_docs = source.scan()
        return [self.process_raw_document(doc) for doc in raw_docs]

    def reprocess_document(self, doc_id: int) -> PipelineResult:
        """Reprocess an existing document by ID, clearing and recomputing extraction."""
        doc = self.repo.get_document_by_id(doc_id)
        if not doc:
            raise ValueError(f"Document with ID {doc_id} not found")

        self.repo.delete_invoice_by_document_id(doc_id)
        self.repo.log_event(doc_id, "pipeline", f"Reprocessing document #{doc_id}")
        self.session.commit()

        stored_path = Path(doc.stored_path)
        return self._process_pipeline_stages(doc, stored_path)
