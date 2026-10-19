# InvoiceFlow 🧾⚡

[![CI](https://github.com/taksh30/invoiceflow/actions/workflows/ci.yml/badge.svg)](https://github.com/taksh30/invoiceflow/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type%20checked-mypy%20strict-brightgreen.svg)](https://github.com/python/mypy)
[![Database: SQLite / PostgreSQL](https://img.shields.io/badge/database-SQLite%20%7C%20PostgreSQL-blue.svg)](https://www.sqlalchemy.org/)

**InvoiceFlow** is a production-ready, automated invoice and receipt processor. It monitors folders or IMAP email inboxes, classifies and extracts vendor, invoice number, date, tax, and totals from digital and scanned documents, cross-validates totals, deduplicates copies, and exports monthly reports to CSV, multi-sheet Excel workbooks, or Google Sheets.

---

## 🏗️ Architecture

InvoiceFlow follows a strictly decoupled, stage-isolated pipeline architecture where each stage acts as a pure, testable unit with per-document error isolation.

```mermaid
flowchart TD
    subgraph Sources ["Ingestion Sources"]
        F["Folder Watcher\n(sources/folder.py)"]
        E["IMAP Email Inbox\n(sources/email_imap.py)"]
    end

    subgraph Pipeline ["Processing Pipeline"]
        I["1. Ingest & SHA-256\n(ingest.py)"]
        C["2. Classify Document\n(extract/classify.py)"]
        T["3. Text & Layout OCR\n(extract/text.py)"]
        FE["4. Field Extractors\n(extract/fields.py)"]
        V["5. Validation Engine\n(validate.py)"]
        D["6. Deduplication\n(dedupe.py)"]
        P["7. Persistence\n(db/repository.py)"]
    end

    subgraph Storage ["Databases & Storage"]
        Raw["Raw File Store\n(data/raw/)"]
        DB[("Database\nSQLite / PostgreSQL")]
        Audit[("Audit Log\nprocessing_events")]
    end

    subgraph Exporters ["Export Destinations"]
        CSV["CSV File\n(export/csv_xlsx.py)"]
        XLSX["Multi-Sheet Excel\n(export/csv_xlsx.py)"]
        GSheets["Google Sheets\n(export/sheets.py)"]
    end

    F --> I
    E --> I
    I --> Raw
    I --> C
    C --> T
    T --> FE
    FE --> V
    V --> D
    D --> P
    P --> DB
    P --> Audit
    DB --> CSV
    DB --> XLSX
    DB --> GSheets
```

---

## 🎬 Demo

<!-- DEMO_GIF_PLACEHOLDER: Add your terminal recording or demo GIF below -->
![InvoiceFlow Terminal Demo](https://raw.githubusercontent.com/taksh30/invoiceflow/main/docs/assets/invoiceflow-demo.gif)
> *Placeholder: Run `invoiceflow process ./fixtures/invoices` to observe real-time OCR extraction, confidence scoring, and table summary generation.*

---

## 🚀 Quickstart

### Prerequisites
- Python 3.12+
- System packages for OCR and PDF rasterization:
  - **macOS** (via Homebrew):
    ```bash
    brew install tesseract poppler
    ```
  - **Debian / Ubuntu**:
    ```bash
    sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-eng poppler-utils
    ```

### Local Installation
```bash
git clone https://github.com/taksh30/invoiceflow.git
cd invoiceflow

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Configuration
Copy the sample environment file:
```bash
cp .env.example .env
```
Key settings in `.env`:
```ini
# Storage & Database
INVOICEFLOW_DATA_DIR=data
INVOICEFLOW_RAW_DIR=data/raw
INVOICEFLOW_DATABASE_URL=sqlite:///data/invoiceflow.db
# Switch to PostgreSQL:
# INVOICEFLOW_DATABASE_URL=postgresql+psycopg://invoiceflow:invoiceflow@localhost:5432/invoiceflow

# Logging
INVOICEFLOW_LOG_LEVEL=INFO
INVOICEFLOW_LOG_JSON=false

# Defaults
INVOICEFLOW_DEFAULT_CURRENCY=INR
INVOICEFLOW_DEFAULT_LOCALE=IN
```

---

## 🐳 Docker & Docker Compose

### Running with Docker Compose (App + PostgreSQL)
```bash
# Build and start services
docker compose up --build

# Run a CLI command inside the container
docker compose run --rm app process /app/fixtures/invoices
```

### Switching to PostgreSQL
InvoiceFlow seamlessly supports PostgreSQL via `psycopg` (v3). Set the connection URL:
```bash
INVOICEFLOW_DATABASE_URL=postgresql+psycopg://invoiceflow:invoiceflow@localhost:5432/invoiceflow invoiceflow process ./invoices
```
Or set `INVOICEFLOW_DATABASE_URL` in `.env` / `docker-compose.yml`.

---

## 💻 CLI Command Reference

All CLI commands are powered by Typer and Rich:

```bash
# Process a single file or directory
invoiceflow process ./path/to/invoice.pdf

# Watch a directory for incoming files (polling daemon)
invoiceflow watch ./inbox_folder --interval 5

# Poll UNSEEN invoice attachments from IMAP mailbox
invoiceflow poll-email --limit 20

# List stored invoices by status (processed, needs_review, duplicate, failed)
invoiceflow list --status needs_review

# Inspect invoice details and audit trail
invoiceflow show 1

# Force reprocess an invoice through the pipeline
invoiceflow reprocess 1

# Export monthly data to CSV, XLSX, or Google Sheets
invoiceflow export --month 2026-03 --format xlsx --output ./data/exports
invoiceflow export --month 2026-03 --format csv
invoiceflow export --month 2026-03 --format sheets --spreadsheet-id <SPREADSHEET_ID>

# Structured JSON logging
invoiceflow --json-log process ./path/to/invoice.pdf
```

---

## 🔬 Testing & Quality Verification

```bash
# Run pytest test suite
pytest -q

# Run Ruff linter and formatter checks
ruff check .
ruff format --check .

# Run Mypy static type checking
mypy src

# Run pre-commit checks
pre-commit run --all-files
```

---

## ⚠️ Limitations

While InvoiceFlow is tuned for high-volume commercial invoices and receipts, the following limitations currently apply:

1. **Handwritten Invoices & Receipts**: Standard OCR models (`pytesseract`) achieve peak accuracy on printed typography; handwritten text or informal carbon-copy slips may produce low confidence scores and require manual review.
2. **Complex Multi-Page Nested Tables**: The rule-based extraction engine aggregates total, tax, and subtotal figures across documents; deeply nested tabular line items spanning arbitrary column alignments require dedicated table-boundary models or LLM assistance.
3. **Multi-Currency Conversion**: When invoices feature multiple currency conversions or cross-border VAT conversions within a single document, the system extracts the primary transactional total and currency symbol without live FX conversion.
4. **Extreme Skew or Inverted Scans**: Documents rotated beyond 45 degrees or inverted photo captures may require pre-processing orientation alignment prior to ingestion.
5. **LLM Fallback**: Scheduled for Phase P13 to seamlessly assist with ambiguous layouts and low-confidence extractions.
