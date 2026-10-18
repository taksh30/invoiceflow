"""SQLAlchemy 2.0 database tables for documents, invoices, and audit events."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from invoiceflow.db.base import Base


class DocumentRow(Base):
    """Database representation of an ingested document."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    invoice: Mapped["InvoiceRow | None"] = relationship(
        back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    events: Mapped[list["ProcessingEventRow"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class InvoiceRow(Base):
    """Database representation of an extracted and validated invoice."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    sgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    igst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    confidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    duplicate_of: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped[DocumentRow] = relationship(back_populates="invoice")

    __table_args__ = (
        Index("ix_invoices_fuzzy", "vendor_name", "invoice_number", "total", "invoice_date"),
    )


class ProcessingEventRow(Base):
    """Database representation of an audit event recorded during processing."""

    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped[DocumentRow] = relationship(back_populates="events")
