# Tasks

Legend: [ ] todo  [~] in progress  [x] done

## Phases
- [x] P1  Scaffold, tooling, config, logging
- [x] P2  Domain models + utils (money, dates)
- [x] P3  Database layer + repositories
- [ ] P4  Folder source + ingest (hashing, storage)
- [ ] P5  Classification + text extraction (pdfplumber, OCR)
- [ ] P6  Field extractors + rule files
- [ ] P7  Validation + confidence scoring
- [ ] P8  Duplicate detection
- [ ] P9  Pipeline orchestration + CLI
- [ ] P10 Email (IMAP) source
- [ ] P11 Exports (CSV/XLSX + Google Sheets)
- [ ] P12 Hardening (retries, logging, Docker, CI, README)
- [ ] P13 Advanced (LLM fallback, review UI, Tally/QuickBooks, Postgres)

## Current phase
P4

## Session Log
- P1 complete: Configured project tooling, pyproject.toml, .gitignore, .env.example, config.py, utils/logging.py, errors.py, empty Typer CLI, .pre-commit-config.yaml, and smoke/unit tests (10/10 passing, 95% coverage).
- P2 complete: Implemented domain models (RawDocument, FieldResult, ExtractedInvoice with Pydantic v2 validators and StrEnums), money parser (supporting Indian, US, and EU formatting, OCR fixes, and scale enforcement), and date parser (handling locale ambiguity and date sanity). 32 tests passing, 94% coverage.
- P3 complete: Implemented SQLAlchemy 2.0 tables (DocumentRow, InvoiceRow, ProcessingEventRow), InvoiceRepository (add_document, get_by_hash, add_invoice, find_candidates, list_by_month, log_event), and Alembic setup. 38 tests passing, 95% coverage.
- Next: P4 Folder source + ingest (hashing, storage).

## Open Questions / Decisions
(none yet)
