"""Unit tests for the InvoiceFlow Typer CLI commands."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from invoiceflow.cli import app
from invoiceflow.models import DocumentSource, RawDocument

runner = CliRunner()
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "invoices"


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configure isolated environment variables for CLI execution."""
    db_file = tmp_path / "test_cli.db"
    raw_dir = tmp_path / "raw"
    export_dir = tmp_path / "exports"

    monkeypatch.setenv("INVOICEFLOW_DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("INVOICEFLOW_RAW_DIR", str(raw_dir))
    monkeypatch.setenv("INVOICEFLOW_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("INVOICEFLOW_LOG_DIR", str(tmp_path / "logs"))
    return tmp_path


def test_cli_help() -> None:
    """Verify CLI help text displays available commands."""
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    assert "InvoiceFlow: Automated invoice and receipt auto-processor" in res.output
    assert "process" in res.output
    assert "watch" in res.output
    assert "list" in res.output
    assert "show" in res.output
    assert "reprocess" in res.output


def test_cli_process_single_file(cli_env: Path) -> None:
    """Verify processing a single invoice file via CLI."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    res = runner.invoke(app, ["process", str(sample_file)])
    assert res.exit_code == 0
    assert "Processing Results" in res.output
    assert "inv_in_01.pdf" in res.output
    assert "Reliance Retail" in res.output


def test_cli_process_directory(cli_env: Path, tmp_path: Path) -> None:
    """Verify processing a folder containing invoices via CLI."""
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    (batch_dir / "inv_01.pdf").write_bytes((FIXTURES_DIR / "inv_in_01.pdf").read_bytes())
    (batch_dir / "inv_02.pdf").write_bytes((FIXTURES_DIR / "inv_in_02.pdf").read_bytes())

    res = runner.invoke(app, ["process", str(batch_dir)])
    assert res.exit_code == 0
    assert "Processing Results" in res.output
    assert "inv_01.pdf" in res.output
    assert "inv_02.pdf" in res.output


def test_cli_list_command(cli_env: Path) -> None:
    """Verify listing documents with and without status filter."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    runner.invoke(app, ["process", str(sample_file)])

    res_all = runner.invoke(app, ["list"])
    assert res_all.exit_code == 0
    assert "Documents" in res_all.output
    assert "inv_in_01.pdf" in res_all.output

    res_filtered = runner.invoke(app, ["list", "--status", "processed"])
    assert res_filtered.exit_code == 0


def test_cli_show_command(cli_env: Path) -> None:
    """Verify show command displays document, invoice, and audit logs."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    runner.invoke(app, ["process", str(sample_file)])

    res_valid = runner.invoke(app, ["show", "1"])
    assert res_valid.exit_code == 0
    assert "Document #1" in res_valid.output
    assert "Invoice Details" in res_valid.output
    assert "Audit Log" in res_valid.output

    res_invalid = runner.invoke(app, ["show", "9999"])
    assert res_invalid.exit_code == 1
    assert "Document with ID 9999 not found" in res_invalid.output


def test_cli_reprocess_command(cli_env: Path) -> None:
    """Verify reprocess command triggers re-extraction for a document."""
    sample_file = FIXTURES_DIR / "inv_in_01.pdf"
    runner.invoke(app, ["process", str(sample_file)])

    res_valid = runner.invoke(app, ["reprocess", "1"])
    assert res_valid.exit_code == 0
    assert "Processing Results" in res_valid.output

    res_invalid = runner.invoke(app, ["reprocess", "9999"])
    assert res_invalid.exit_code == 1
    assert "Document with ID 9999 not found" in res_invalid.output


def test_cli_watch_command(cli_env: Path, tmp_path: Path) -> None:
    """Verify watch command polls directory and stops cleanly on interrupt."""
    watch_dir = tmp_path / "incoming"
    watch_dir.mkdir()

    sample_doc = RawDocument(
        content=(FIXTURES_DIR / "inv_in_01.pdf").read_bytes(),
        filename="watch_inv.pdf",
        source=DocumentSource.FOLDER,
        source_ref=str(watch_dir / "watch_inv.pdf"),
    )

    def mock_watch(*args: object, **kwargs: object):
        yield sample_doc
        raise KeyboardInterrupt

    with patch("invoiceflow.sources.folder.FolderSource.watch", side_effect=mock_watch):
        res = runner.invoke(app, ["watch", str(watch_dir)])

    assert res.exit_code == 0
    assert "Watching directory" in res.output
    assert "Watch mode stopped." in res.output
    assert "watch_inv.pdf" in res.output


def test_cli_poll_email_missing_credentials(cli_env: Path) -> None:
    """Verify poll-email fails with code 1 when IMAP settings are not configured."""
    res = runner.invoke(app, ["poll-email"])
    assert res.exit_code == 1
    assert "Missing IMAP credentials" in res.output


def test_cli_poll_email_success(cli_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify poll-email connects, fetches attachments, and processes them."""
    monkeypatch.setenv("INVOICEFLOW_IMAP_HOST", "imap.mailcorp.com")
    monkeypatch.setenv("INVOICEFLOW_IMAP_USER", "invoices@mailcorp.com")
    monkeypatch.setenv("INVOICEFLOW_IMAP_PASSWORD", "secret123")

    email_doc = RawDocument(
        content=(FIXTURES_DIR / "inv_in_01.pdf").read_bytes(),
        filename="email_inv.pdf",
        source=DocumentSource.EMAIL,
        source_ref="imap://invoices@mailcorp.com@imap.mailcorp.com/INBOX#uid=99&file=email_inv.pdf",
    )

    with patch(
        "invoiceflow.sources.email_imap.ImapEmailSource.fetch_documents",
        return_value=[email_doc],
    ):
        res = runner.invoke(app, ["poll-email"])

    assert res.exit_code == 0
    assert "Connecting to IMAP" in res.output
    assert "Processing Results" in res.output
    assert "email_inv.pdf" in res.output
    assert "Reliance Retail" in res.output


def test_cli_poll_email_no_documents(cli_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify poll-email outputs friendly message when no unseen invoices exist."""
    monkeypatch.setenv("INVOICEFLOW_IMAP_HOST", "imap.mailcorp.com")
    monkeypatch.setenv("INVOICEFLOW_IMAP_USER", "invoices@mailcorp.com")
    monkeypatch.setenv("INVOICEFLOW_IMAP_PASSWORD", "secret123")

    with patch(
        "invoiceflow.sources.email_imap.ImapEmailSource.fetch_documents",
        return_value=[],
    ):
        res = runner.invoke(app, ["poll-email"])

    assert res.exit_code == 0
    assert "Connecting to IMAP" in res.output
    assert "No unseen invoices or attachments found" in res.output
