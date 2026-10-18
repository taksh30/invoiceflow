"""Document ingestion service with SHA-256 hashing, storage, and deduplication."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.db.tables import DocumentRow
from invoiceflow.errors import IngestError
from invoiceflow.models import DocumentType, ProcessingStatus, RawDocument
from invoiceflow.sources.folder import SUPPORTED_EXTENSIONS


def compute_sha256(content: bytes) -> str:
    """Compute hex-encoded SHA-256 digest of binary content."""
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class IngestResult:
    """Outcome of an ingestion attempt."""

    document: DocumentRow
    is_duplicate: bool
    stored_path: Path


class IngestionService:
    """Coordinates file integrity validation, persistence, and registration."""

    def __init__(self, repository: InvoiceRepository, raw_dir: Path) -> None:
        """Initialize ingestion service with repository and raw storage directory."""
        self.repository = repository
        self.raw_dir = raw_dir

    def _determine_initial_doc_type(self, suffix: str) -> DocumentType:
        """Assign preliminary document type based on file extension."""
        if suffix.lower() == ".pdf":
            return DocumentType.TEXT_PDF
        return DocumentType.IMAGE

    def ingest(self, raw_doc: RawDocument) -> IngestResult:
        """Ingest a RawDocument, returning early if content hash already exists."""
        suffix = Path(raw_doc.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise IngestError(f"Unsupported file type: {raw_doc.filename!r}")

        file_hash = compute_sha256(raw_doc.content)
        existing = self.repository.get_by_hash(file_hash)
        if existing is not None:
            return IngestResult(
                document=existing,
                is_duplicate=True,
                stored_path=Path(existing.stored_path),
            )

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        dest_path = self.raw_dir / f"{file_hash}{suffix}"
        dest_path.write_bytes(raw_doc.content)

        doc = self.repository.add_document(
            file_sha256=file_hash,
            original_name=raw_doc.filename,
            stored_path=str(dest_path),
            source=raw_doc.source.value,
            source_ref=raw_doc.source_ref,
            doc_type=self._determine_initial_doc_type(suffix).value,
            status=ProcessingStatus.PROCESSED.value,
        )

        self.repository.log_event(
            document_id=doc.id,
            stage="ingest",
            message=f"Ingested {raw_doc.filename} to {dest_path.name}",
            level="INFO",
        )

        return IngestResult(document=doc, is_duplicate=False, stored_path=dest_path)
