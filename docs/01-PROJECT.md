# Project: InvoiceFlow

## Problem
Freelancers and small businesses lose hours to manual bookkeeping. InvoiceFlow
ingests invoices/receipts automatically and produces clean, deduplicated records.

## Goals (MVP)
- Ingest from: watched folder, IMAP email inbox
- Handle: text PDFs, scanned PDFs, images (JPG/PNG)
- Extract: vendor, invoice number, date, currency, subtotal, tax, total, tax ID
- Validate + score confidence per field
- Detect duplicates (exact file hash + fuzzy business-key match)
- Store in SQLite (Postgres-ready via SQLAlchemy)
- Export monthly CSV/XLSX; optional Google Sheets sync
- CLI-first (typer)

## Non-Goals (MVP)
- No web UI, no multi-user auth, no payments, no line-item extraction
  (line items are a future feature)

## Target locale
Primary: India (GST: CGST/SGST/IGST, GSTIN, INR, dd/mm/yyyy dates).
Must also parse US/EU formats (USD/EUR, mm/dd/yyyy, 1.234,56 style numbers).

## Future (post-MVP)
LLM extraction fallback, review UI for low-confidence fields, Tally and
QuickBooks exports, PostgreSQL deployment, Gmail API.

## Definition of Done (MVP)
- 90%+ correct total/date/vendor on the 30-document fixture set
- Re-running the pipeline never creates duplicate records
- Failures never crash a batch; they are logged with a reason and status
- Test coverage >= 80% on core modules
