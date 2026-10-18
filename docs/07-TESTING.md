# Testing
- Framework: pytest. Layout: tests/unit, tests/integration, tests/fixtures
- Fixtures: tests/fixtures/invoices/ holds ~30 SYNTHETIC or anonymized files
  (text PDF, scanned PDF, JPG, multiple vendors, Indian GST + US/EU formats)
- Each fixture has <name>.expected.json with ground-truth fields
- Unit tests: money parsing, date parsing, each extractor, dedupe logic
- Integration: full pipeline on fixtures, assert accuracy report
- Accuracy test: per-field accuracy printed; fails if total/date/vendor < 90%
- Mock IMAP and Google Sheets; never hit real services in tests
- OCR tests marked @pytest.mark.ocr (skippable if tesseract is missing)
- Coverage target: >= 80% core (extract/, validate.py, dedupe.py, pipeline.py)
