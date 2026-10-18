# Architecture

## Pipeline (each stage is a pure, testable unit)
Source -> Ingest -> Classify -> Extract Text -> Extract Fields -> Validate
-> Dedupe -> Persist -> Export

| Stage | Module | Responsibility |
|---|---|---|
| Source | sources/folder.py, sources/email_imap.py | Yield RawDocument (bytes, filename, origin) |
| Ingest | ingest.py | SHA-256 hash, save to data/raw/, create Document row |
| Classify | extract/classify.py | text-PDF vs scanned-PDF vs image |
| Extract Text | extract/text.py | pdfplumber for text PDFs; pypdfium2 + pytesseract for scans/images |
| Extract Fields | extract/fields.py | Rule-based extractors returning FieldResult(value, confidence, source_span) |
| Validate | validate.py | Pydantic model + cross-checks (subtotal + tax ~= total) |
| Dedupe | dedupe.py | Exact (hash) then fuzzy (vendor+number+total+date) |
| Persist | db/ | SQLAlchemy repositories |
| Export | export/ | CSV, XLSX, Google Sheets, (later) Tally/QuickBooks |

## Package layout
src/invoiceflow/
  config.py          # pydantic-settings, reads .env
  models.py          # domain dataclasses/pydantic (see 03-DATA-MODEL)
  pipeline.py        # orchestrates stages, per-document error isolation
  cli.py             # typer app
  sources/           # folder.py, email_imap.py
  extract/           # classify.py, text.py, fields.py, rules/
  db/                # base.py, tables.py, repository.py
  export/            # csv_xlsx.py, sheets.py
  utils/             # money.py, dates.py, logging.py

## Key design decisions
- Extractor interface: FieldExtractor.extract(text, layout) -> FieldResult | None.
  New rules or an LLM fallback plug in without touching the pipeline.
- Error isolation: one bad document never stops the batch. Each document ends
  in a status: processed | needs_review | duplicate | failed.
- Idempotency: re-processing the same file is a no-op (hash check).
- Money: use Decimal, never float. Dates: timezone-naive date objects.
- Retries (tenacity) only on I/O: IMAP, Sheets API. Never on parsing.
- Config via env vars; no secrets in code or the DB.
