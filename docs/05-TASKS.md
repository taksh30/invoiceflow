# Tasks

Legend: [ ] todo  [~] in progress  [x] done

## Phases
- [x] P1  Scaffold, tooling, config, logging
- [x] P2  Domain models + utils (money, dates)
- [x] P3  Database layer + repositories
- [x] P4  Folder source + ingest (hashing, storage)
- [x] P5  Classification + text extraction (pdfplumber, OCR)
- [x] P6  Field extractors + rule files
- [x] P7  Validation + confidence scoring
- [x] P8  Duplicate detection
- [x] P9  Pipeline orchestration + CLI
- [x] P10 Email (IMAP) source
- [x] P11 Exports (CSV/XLSX + Google Sheets)
- [ ] P12 Hardening (retries, logging, Docker, CI, README)
- [ ] P13 Advanced (LLM fallback, review UI, Tally/QuickBooks, Postgres)

## Current phase
P12

## Session Log
- P1 complete: Configured project tooling, pyproject.toml, .gitignore, .env.example, config.py, utils/logging.py, errors.py, empty Typer CLI, .pre-commit-config.yaml, and smoke/unit tests (10/10 passing, 95% coverage).
- P2 complete: Implemented domain models (RawDocument, FieldResult, ExtractedInvoice with Pydantic v2 validators and StrEnums), money parser (supporting Indian, US, and EU formatting, OCR fixes, and scale enforcement), and date parser (handling locale ambiguity and date sanity). 32 tests passing, 94% coverage.
- P3 complete: Implemented SQLAlchemy 2.0 tables (DocumentRow, InvoiceRow, ProcessingEventRow), InvoiceRepository (add_document, get_by_hash, add_invoice, find_candidates, list_by_month, log_event), and Alembic setup. 38 tests passing, 95% coverage.
- P4 complete: Implemented FolderSource (scanning, polling watcher, .pdf/.jpg/.jpeg/.png filter, seen tracking) and IngestionService (SHA-256 computation, raw file persistence, DB registration, idempotency on hash match). 46 tests passing, 96% coverage.
- P5 complete: Implemented classify_document, TextResult and WordBox models, pdfplumber digital extraction, Pillow image preprocessing, and pypdfium2 + pytesseract OCR. Added 3 fixtures and verified OCR tests. 55 tests passing, 96% coverage.
- P6 complete: Implemented modular FieldExtractors and YAML rule configuration for total, subtotal, tax/GST splits, invoice number, date, vendor, tax ID, and currency. Generated 30 benchmark fixtures with ground-truth expected JSON. Evaluation report passed all DoD thresholds (100% total, 100% date, 100% vendor, 97% invoice number). 66 tests passing, 93% coverage.
- P7 complete: Implemented validate.py with ValidationResult, subtotal + tax arithmetic cross-checks (tolerance <= 1.00 boosts confidence +0.05, diff > 1.00 flags needs_review), GST split consistency, key field presence and confidence threshold rules (< 0.60 flags needs_review), and build_and_validate helper. 77 tests passing, 93% coverage.
- P8 complete: Implemented dedupe.py with normalize_vendor, vendor_similarity via rapidfuzz, find_duplicate comparing normalized vendor (>= 90% similarity), invoice number, total, and date, marking duplicate_of and status=duplicate. Tested exact matches, re-scanned copies, near-misses, and missing numbers. 87 tests passing, 94% coverage.
- P9 complete: Implemented Pipeline orchestrator (Ingest -> Classify -> Text -> Fields -> Validate -> Dedupe -> Persist with per-document error isolation and audit logging) and Typer CLI commands (process, watch, list, show, reprocess). Added unit and E2E integration tests running all 30 benchmark fixtures; verified zero duplicates on re-run. 103 tests passing, all linters clean.
- P10 complete: Implemented ImapEmailSource (SSL connection, UNSEEN message search, RFC 2047 attachment decoding, \\Seen marking, local seen-UID tracking, and tenacity connection retries) and Typer CLI command poll-email. Added 12 unit tests with mocked IMAP server. 115 tests passing, all linters clean.
- P11 complete: Implemented export/csv_xlsx.py (multi-sheet Excel workbook with Invoices and Vendor Summary, and CSV export via pandas) and export/sheets.py (Google Sheets append via Service Account, idempotent by invoice ID with tenacity retries). Added Typer CLI command export and 14 unit tests. 129 tests passing, all linters clean.
- Next: P12 Hardening (retries, logging, Docker, CI, README).

## Open Questions / Decisions
(none yet)
