# Extraction Rules

## General
- Normalize text first: collapse whitespace, unify unicode, fix common OCR
  confusions (O/0, l/1, S/5) ONLY inside numeric tokens.
- Every extractor returns a confidence in [0,1]. Rules:
  - keyword-anchored + valid format: 0.9
  - pattern match without anchor: 0.6
  - fallback heuristic: 0.4
  - OCR text: multiply by 0.9

## Fields
| Field | Strategy |
|---|---|
| total | Anchor on "Grand Total", "Total Amount", "Amount Due", "Net Payable", "Balance Due"; take the largest plausible amount near the anchor; fallback = max amount on last page |
| subtotal | "Subtotal", "Taxable Value", "Sub Total" |
| tax_total | Sum of CGST+SGST+IGST, or "Tax", "VAT", "GST" anchors |
| invoice_number | Anchors: "Invoice No", "Inv #", "Bill No", "Receipt No"; alphanumeric with -/ allowed |
| invoice_date | Anchors: "Invoice Date", "Date", "Dated"; parse dd/mm/yyyy, dd-MMM-yyyy, yyyy-mm-dd; ambiguity: prefer dd/mm when locale is IN |
| vendor_name | Top ~8 lines of page 1, skipping lines with "invoice"/"bill to"/addresses; prefer line near GSTIN or the logo area; later: match a known-vendor table |
| vendor_tax_id | GSTIN regex: \b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b |
| currency | Symbols and codes: Rs/₹/INR, $/USD, €/EUR, £/GBP |

## Number parsing
- Support 1,23,456.78 (Indian grouping), 1,234.56, 1.234,56
- Strip currency symbols; return Decimal; reject if more than 2 decimals

## Cross-validation
- If subtotal and tax_total exist: |subtotal + tax_total - total| <= 1.00 -> boost
  confidence +0.05; else flag needs_review
- total must be > 0
- Any key field confidence < 0.6 -> status needs_review

## Rule files
Rules are data-driven where possible: extract/rules/*.yaml (anchors, patterns),
loaded at startup. Adding a vendor-specific rule must not require code changes.
