"""Unit tests for folder scanning and directory watcher."""

from pathlib import Path

from invoiceflow.models import DocumentSource
from invoiceflow.sources.folder import FolderSource


def test_scan_folder_filtering(tmp_path: Path) -> None:
    """Verify only non-hidden supported extensions (.pdf, .jpg, .jpeg, .png) are yielded."""
    (tmp_path / "invoice.pdf").write_bytes(b"%PDF-sample")
    (tmp_path / "receipt.JPG").write_bytes(b"\xff\xd8\xff-jpg")
    (tmp_path / "bill.jpeg").write_bytes(b"\xff\xd8\xff-jpeg")
    (tmp_path / "snap.png").write_bytes(b"\x89PNG-png")

    # Unsupported or hidden files
    (tmp_path / "notes.txt").write_text("irrelevant notes")
    (tmp_path / ".hidden.pdf").write_bytes(b"hidden")
    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()
    (sub_dir / "nested.pdf").write_bytes(b"nested")

    source = FolderSource(tmp_path)
    docs = list(source.scan())

    assert len(docs) == 4
    filenames = {d.filename for d in docs}
    assert filenames == {"invoice.pdf", "receipt.JPG", "bill.jpeg", "snap.png"}

    pdf_doc = next(d for d in docs if d.filename == "invoice.pdf")
    assert pdf_doc.content == b"%PDF-sample"
    assert pdf_doc.source == DocumentSource.FOLDER
    assert pdf_doc.source_ref == str((tmp_path / "invoice.pdf").resolve())


def test_scan_folder_skips_already_seen(tmp_path: Path) -> None:
    """Verify scanning multiple times skips already yielded files until new ones appear."""
    (tmp_path / "first.pdf").write_bytes(b"first")
    source = FolderSource(tmp_path)

    docs1 = list(source.scan())
    assert len(docs1) == 1
    assert docs1[0].filename == "first.pdf"

    # Second scan: no new files
    docs2 = list(source.scan())
    assert len(docs2) == 0

    # Add a second file
    (tmp_path / "second.png").write_bytes(b"second")
    docs3 = list(source.scan())
    assert len(docs3) == 1
    assert docs3[0].filename == "second.png"


def test_watch_folder_polling(tmp_path: Path) -> None:
    """Verify watch generator polls directory and stops after max_iterations."""
    (tmp_path / "initial.pdf").write_bytes(b"initial")
    source = FolderSource(tmp_path)

    yielded = list(source.watch(poll_interval=0.01, max_iterations=2))
    assert len(yielded) == 1
    assert yielded[0].filename == "initial.pdf"


def test_scan_nonexistent_directory(tmp_path: Path) -> None:
    """Verify scanning nonexistent directory returns empty iterator gracefully."""
    non_existent = tmp_path / "does_not_exist"
    source = FolderSource(non_existent)
    assert list(source.scan()) == []
