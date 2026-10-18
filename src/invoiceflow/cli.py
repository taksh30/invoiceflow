"""Command-line interface entry point for InvoiceFlow."""

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from invoiceflow.config import Settings
from invoiceflow.db.base import create_db_engine, get_session_factory, init_db
from invoiceflow.db.repository import InvoiceRepository
from invoiceflow.db.tables import DocumentRow, InvoiceRow, ProcessingEventRow
from invoiceflow.pipeline import Pipeline, PipelineResult
from invoiceflow.sources.email_imap import ImapEmailSource
from invoiceflow.sources.folder import FolderSource

app = typer.Typer(
    name="invoiceflow",
    help="InvoiceFlow: Automated invoice and receipt auto-processor.",
    no_args_is_help=True,
)
console = Console(width=120)


def _get_pipeline(locale: str = "IN") -> tuple[Pipeline, InvoiceRepository, Any]:
    """Initialize database session and pipeline instance."""
    settings = Settings()
    settings.ensure_directories()
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session = get_session_factory(engine)()
    repo = InvoiceRepository(session)
    pipeline = Pipeline(
        session=session,
        raw_storage_dir=settings.raw_dir,
        default_locale=locale or settings.default_locale,
    )
    return pipeline, repo, session


def _render_results_table(results: list[PipelineResult]) -> None:
    """Render pipeline execution results in a Rich table."""
    table = Table(title="Processing Results", show_lines=False)
    table.add_column("Doc ID", style="cyan", justify="right")
    table.add_column("Filename", style="bold", overflow="fold")
    table.add_column("Status", style="magenta")
    table.add_column("Vendor", style="green")
    table.add_column("Total", justify="right")
    table.add_column("Currency")
    table.add_column("Duplicate Of", justify="right")

    for res in results:
        inv = res.invoice
        vendor = inv.vendor_name if inv else "-"
        total = f"{inv.total:.2f}" if inv else "-"
        curr = inv.currency if inv else "-"
        dup = str(inv.duplicate_of) if inv and inv.duplicate_of else "-"
        status_style = "green" if res.status.value == "processed" else "yellow"
        if res.status.value == "failed":
            status_style = "red"
        table.add_row(
            str(res.document.id),
            res.document.original_name,
            f"[{status_style}]{res.status.value}[/{status_style}]",
            vendor,
            total,
            curr,
            dup,
        )

    console.print(table)


@app.command(name="process")
def process_command(
    path: Annotated[Path, typer.Argument(help="Path to invoice file or directory")],
    locale: Annotated[str, typer.Option(help="Default country locale (IN, US, EU)")] = "IN",
) -> None:
    """Process a single document or batch of documents in a directory."""
    pipeline, _, session = _get_pipeline(locale)
    try:
        if path.is_dir():
            results = pipeline.process_folder(path)
        else:
            results = [pipeline.process_file(path)]
        _render_results_table(results)
    finally:
        session.close()


@app.command(name="watch")
def watch_command(
    path: Annotated[Path, typer.Argument(help="Directory path to watch for incoming documents")],
    interval: Annotated[float, typer.Option(help="Polling interval in seconds")] = 2.0,
    locale: Annotated[str, typer.Option(help="Default country locale")] = "IN",
) -> None:
    """Continuously poll a directory for new incoming invoices and receipts."""
    pipeline, _, session = _get_pipeline(locale)
    source = FolderSource(path)
    console.print(f"[bold green]Watching directory:[/bold green] {path.resolve()}")
    try:
        for new_doc in source.watch(poll_interval=interval):
            result = pipeline.process_raw_document(new_doc)
            _render_results_table([result])
    except KeyboardInterrupt:
        console.print("\n[yellow]Watch mode stopped.[/yellow]")
    finally:
        session.close()


@app.command(name="poll-email")
def poll_email_command(
    folder: Annotated[str | None, typer.Option(help="Override IMAP mailbox folder to poll")] = None,
    locale: Annotated[str, typer.Option(help="Default country locale (IN, US, EU)")] = "IN",
) -> None:
    """Poll configured IMAP mailbox over SSL for new invoice attachments."""
    settings = Settings()
    if not settings.imap_host or not settings.imap_user or not settings.imap_password:
        console.print(
            "[red]Error:[/red] Missing IMAP credentials. Configure INVOICEFLOW_IMAP_HOST, "
            "INVOICEFLOW_IMAP_USER, and INVOICEFLOW_IMAP_PASSWORD in environment or .env file."
        )
        raise typer.Exit(code=1)

    mailbox_folder = folder or settings.imap_folder
    console.print(
        f"[bold green]Connecting to IMAP:[/bold green] {settings.imap_user}@{settings.imap_host}:"
        f"{settings.imap_port}/{mailbox_folder}"
    )

    source = ImapEmailSource(
        host=settings.imap_host,
        port=settings.imap_port,
        user=settings.imap_user,
        password=settings.imap_password,
        folder=mailbox_folder,
    )

    pipeline, _, session = _get_pipeline(locale)
    try:
        raw_docs = source.fetch_documents()
        if not raw_docs:
            console.print("[yellow]No unseen invoices or attachments found.[/yellow]")
            return

        results = [pipeline.process_raw_document(doc) for doc in raw_docs]
        _render_results_table(results)
    finally:
        session.close()


@app.command(name="list")
def list_command(
    status: Annotated[
        str | None,
        typer.Option("--status", "-s", help="Filter status (processed, needs_review, duplicate)"),
    ] = None,
) -> None:
    """List documents and extracted invoices in the database."""
    _, repo, session = _get_pipeline()
    try:
        docs = repo.list_documents(status=status)
        table = Table(title="Documents", show_lines=False)
        table.add_column("ID", justify="right", style="cyan")
        table.add_column("Original Name", style="bold", overflow="fold")
        table.add_column("Ingested At")
        table.add_column("Status", style="magenta")
        table.add_column("Vendor", style="green")
        table.add_column("Total", justify="right")

        for doc in docs:
            inv = repo.get_invoice_by_document_id(doc.id)
            vendor = inv.vendor_name if inv else "-"
            total = f"{inv.total:.2f}" if inv else "-"
            table.add_row(
                str(doc.id),
                doc.original_name,
                doc.ingested_at.strftime("%Y-%m-%d %H:%M"),
                doc.status,
                vendor,
                total,
            )
        console.print(table)
    finally:
        session.close()


def _render_document_details(doc: DocumentRow, inv: InvoiceRow | None) -> None:
    """Render details panel for document and invoice."""
    doc_info = (
        f"ID: {doc.id}\n"
        f"Original Name: {doc.original_name}\n"
        f"SHA-256: {doc.file_sha256}\n"
        f"Type: {doc.doc_type}\n"
        f"Status: {doc.status}\n"
        f"Error: {doc.error or '-'}"
    )
    console.print(Panel(doc_info, title=f"Document #{doc.id}", expand=False))

    if inv:
        inv_info = (
            f"Vendor: {inv.vendor_name}\n"
            f"Tax ID: {inv.vendor_tax_id or '-'}\n"
            f"Invoice No: {inv.invoice_number or '-'}\n"
            f"Date: {inv.invoice_date}\n"
            f"Subtotal: {inv.subtotal}\n"
            f"Tax Total: {inv.tax_total} (CGST: {inv.cgst}, SGST: {inv.sgst}, IGST: {inv.igst})\n"
            f"Total: {inv.total} {inv.currency}\n"
            f"Confidence: {inv.overall_confidence}\n"
            f"Duplicate Of: {inv.duplicate_of or '-'}"
        )
        console.print(Panel(inv_info, title="Invoice Details", expand=False))


def _render_events_table(events: Sequence[ProcessingEventRow]) -> None:
    """Render audit events in a table."""
    if not events:
        return
    ev_table = Table(title="Audit Log", show_lines=False)
    ev_table.add_column("Timestamp", style="dim")
    ev_table.add_column("Stage", style="cyan")
    ev_table.add_column("Level", style="magenta")
    ev_table.add_column("Message")

    for ev in events:
        ev_table.add_row(
            ev.created_at.strftime("%H:%M:%S"),
            ev.stage,
            ev.level,
            ev.message,
        )
    console.print(ev_table)


@app.command(name="show")
def show_command(
    doc_id: Annotated[int, typer.Argument(help="Document ID to inspect")],
) -> None:
    """Display comprehensive details and audit log for a document."""
    _, repo, session = _get_pipeline()
    try:
        doc = repo.get_document_by_id(doc_id)
        if not doc:
            console.print(f"[red]Error:[/red] Document with ID {doc_id} not found.")
            raise typer.Exit(code=1)

        inv = repo.get_invoice_by_document_id(doc_id)
        events = repo.list_events_by_document_id(doc_id)

        _render_document_details(doc, inv)
        _render_events_table(events)
    finally:
        session.close()


@app.command(name="reprocess")
def reprocess_command(
    doc_id: Annotated[int, typer.Argument(help="Document ID to reprocess")],
) -> None:
    """Reprocess an existing document through the extraction pipeline."""
    pipeline, repo, session = _get_pipeline()
    try:
        doc = repo.get_document_by_id(doc_id)
        if not doc:
            console.print(f"[red]Error:[/red] Document with ID {doc_id} not found.")
            raise typer.Exit(code=1)

        result = pipeline.reprocess_document(doc_id)
        _render_results_table([result])
    finally:
        session.close()


@app.callback()
def main() -> None:
    """InvoiceFlow root CLI callback."""


if __name__ == "__main__":
    app()
