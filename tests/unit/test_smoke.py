"""Smoke tests for InvoiceFlow package and CLI."""

from typer.testing import CliRunner

import invoiceflow
from invoiceflow.cli import app

runner = CliRunner()


def test_package_version() -> None:
    """Verify package version is defined."""
    assert invoiceflow.__version__ == "0.1.0"


def test_cli_help() -> None:
    """Verify invoiceflow --help executes successfully and renders help text."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "InvoiceFlow" in result.stdout
    assert "--help" in result.stdout
