"""Folder-based ingestion source scanning and polling watch directory."""

import time
from collections.abc import Iterator
from pathlib import Path

from invoiceflow.models import DocumentSource, RawDocument

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


class FolderSource:
    """Scans and monitors a directory for supported invoice documents."""

    def __init__(self, folder_path: Path) -> None:
        """Initialize folder source with directory path."""
        self.folder_path = folder_path
        self._seen_paths: set[Path] = set()

    def _is_supported_file(self, path: Path) -> bool:
        """Check if path is a regular, non-hidden file with supported extension."""
        return (
            path.is_file()
            and not path.name.startswith(".")
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def _read_raw_document(self, path: Path) -> RawDocument:
        """Read file contents into a RawDocument instance."""
        return RawDocument(
            content=path.read_bytes(),
            filename=path.name,
            source=DocumentSource.FOLDER,
            source_ref=str(path.resolve()),
        )

    def scan(self) -> Iterator[RawDocument]:
        """Scan folder and yield newly found supported documents."""
        if not self.folder_path.exists():
            return

        for path in sorted(self.folder_path.iterdir()):
            if self._is_supported_file(path) and path not in self._seen_paths:
                self._seen_paths.add(path)
                yield self._read_raw_document(path)

    def watch(
        self, poll_interval: float = 2.0, max_iterations: int | None = None
    ) -> Iterator[RawDocument]:
        """Continuously poll folder for new documents at fixed intervals."""
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            yield from self.scan()
            iterations += 1
            if max_iterations is None or iterations < max_iterations:
                time.sleep(poll_interval)
