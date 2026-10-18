# InvoiceFlow: AI Working Agreement

Invoice/receipt auto-processor: watches a folder or IMAP inbox, extracts
vendor, date, tax, total from PDFs/images, stores clean records, exports monthly.

## Read order (only read what the current task needs)
1. docs/05-TASKS.md       -> find the current phase (ALWAYS read first)
2. docs/01-PROJECT.md     -> goals, scope, non-goals
3. docs/02-ARCHITECTURE.md -> pipeline, modules, interfaces
4. docs/03-DATA-MODEL.md  -> DB schema and pydantic models
5. docs/04-EXTRACTION-RULES.md -> regex/layout rules, confidence scoring
6. docs/06-STANDARDS.md   -> code style, error handling, logging
7. docs/07-TESTING.md     -> fixtures and test strategy

## Hard rules
- Work on ONE phase at a time. Do not start the next phase unprompted.
- Before coding a phase: post a short plan (files to create/change) and wait for approval.
- Do not re-explain or rewrite the docs. If a doc is wrong, propose a precise edit.
- Do not read the whole repo. Read only files relevant to the current phase.
- After finishing a phase: run tests + linters, tick the checklist in
  docs/05-TASKS.md, add a 2-3 line note under "Session Log", then stop.
- Never commit real invoices or credentials. Use fixtures in tests/fixtures/.
- Secrets only via environment variables (.env, never committed).

## Stack (fixed)
Python 3.12, pydantic v2, SQLAlchemy 2.0, pandas, pdfplumber, pytesseract,
pypdfium2, Pillow, typer, tenacity, pytest, ruff, mypy.

## Commands
- Install: pip install -e ".[dev]"
- Test: pytest -q
- Lint: ruff check . && ruff format --check . && mypy src
- Run: invoiceflow --help
