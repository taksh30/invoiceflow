"""Command-line interface entry point for InvoiceFlow."""

import typer

app = typer.Typer(
    name="invoiceflow",
    help="InvoiceFlow: Automated invoice and receipt auto-processor.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """InvoiceFlow root CLI callback."""


if __name__ == "__main__":
    app()
