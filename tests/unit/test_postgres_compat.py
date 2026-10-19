"""Tests verifying PostgreSQL compatibility and DATABASE_URL switching."""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from invoiceflow.config import Settings
from invoiceflow.db.base import create_db_engine
from invoiceflow.db.tables import DocumentRow, InvoiceRow, ProcessingEventRow


def test_postgres_engine_creation() -> None:
    """Verify that create_db_engine initializes postgresql+psycopg engine."""
    pg_url = "postgresql+psycopg://invoiceflow:secret@localhost:5432/invoiceflow"
    engine = create_db_engine(pg_url)

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
    # Ensure SQLite-specific connect_args are not attached to PostgreSQL engine
    assert "check_same_thread" not in engine.url.query


def test_database_url_switching_in_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings picks up switched DATABASE_URL for Postgres."""
    custom_pg_url = "postgresql+psycopg://custom_user:custom_pass@postgres_host:5432/custom_db"
    monkeypatch.setenv("INVOICEFLOW_DATABASE_URL", custom_pg_url)

    settings = Settings()
    assert settings.database_url == custom_pg_url

    engine = create_db_engine(settings.database_url)
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_schema_compilation_for_postgresql() -> None:
    """Verify all ORM tables and indexes compile to valid PostgreSQL DDL."""
    pg_dialect = postgresql.dialect()

    # Compile documents table DDL
    docs_ddl = str(CreateTable(DocumentRow.__table__).compile(dialect=pg_dialect))
    assert "CREATE TABLE documents" in docs_ddl
    assert "file_sha256 VARCHAR(64)" in docs_ddl
    assert "ingested_at TIMESTAMP WITH TIME ZONE" in docs_ddl

    # Compile invoices table DDL
    invoices_ddl = str(CreateTable(InvoiceRow.__table__).compile(dialect=pg_dialect))
    assert "CREATE TABLE invoices" in invoices_ddl
    assert "confidence JSON" in invoices_ddl
    assert "total NUMERIC(14, 2)" in invoices_ddl
    assert "FOREIGN KEY(document_id) REFERENCES documents (id)" in invoices_ddl

    # Compile processing_events table DDL
    events_ddl = str(CreateTable(ProcessingEventRow.__table__).compile(dialect=pg_dialect))
    assert "CREATE TABLE processing_events" in events_ddl
    assert "FOREIGN KEY(document_id) REFERENCES documents (id)" in events_ddl

    # Compile ix_invoices_fuzzy index DDL
    for idx in InvoiceRow.__table__.indexes:
        idx_ddl = str(CreateIndex(idx).compile(dialect=pg_dialect))
        assert "CREATE INDEX" in idx_ddl
