# Data Model

## Table: documents
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| file_sha256 | str unique | exact-duplicate key |
| original_name | str | |
| stored_path | str | data/raw/<sha256><ext> |
| source | enum(folder,email) | |
| source_ref | str | email message-id or folder path |
| doc_type | enum(text_pdf,scanned_pdf,image) | |
| status | enum(processed,needs_review,duplicate,failed) | |
| error | str null | failure reason |
| ingested_at | datetime | |

## Table: invoices (1:1 with documents when status != failed)
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| document_id | FK documents | |
| vendor_name | str | normalized |
| vendor_tax_id | str null | e.g. GSTIN |
| invoice_number | str null | |
| invoice_date | date null | |
| currency | str(3) | ISO code, default INR |
| subtotal | Numeric(14,2) null | |
| tax_total | Numeric(14,2) null | |
| cgst / sgst / igst | Numeric(14,2) null | India GST split |
| total | Numeric(14,2) | required |
| confidence | JSON | {field: 0.0-1.0} |
| overall_confidence | float | min or weighted of key fields |
| duplicate_of | FK invoices null | |
| created_at | datetime | |

## Table: processing_events (audit log)
id, document_id, stage, level, message, created_at

## Pydantic models
- RawDocument: content: bytes, filename: str, source: str, source_ref: str
- FieldResult: value: Any, confidence: float, span: str | None
- ExtractedInvoice: all invoice fields + confidences; validators enforce
  Decimal money, ISO currency, date sanity (not in future, not before 2000)

## Indexes
documents(file_sha256) unique; invoices(vendor_name, invoice_number, total, invoice_date)
