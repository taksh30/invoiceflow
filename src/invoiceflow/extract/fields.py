"""Field extraction engines and rules parsing invoice and receipt data."""

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import yaml

from invoiceflow.extract.text import TextResult, WordBox
from invoiceflow.models import ExtractedInvoice, FieldResult
from invoiceflow.utils.dates import parse_date
from invoiceflow.utils.money import parse_money

RULES_FILE_PATH = Path(__file__).parent / "rules" / "rules.yaml"


def _load_rules() -> dict[str, Any]:
    """Load extraction rules from YAML configuration file."""
    if not RULES_FILE_PATH.exists():
        return {}
    with RULES_FILE_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_RULES = _load_rules()


class FieldExtractor(Protocol):
    """Protocol defining the standard field extractor interface."""

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract a field from text and optional layout bounding boxes."""
        ...


def _find_money_candidates(line: str) -> list[Decimal]:
    """Extract all plausible money values from a text line."""
    pattern = (
        r"(?:[₹$€£]\s*)?(?:\d{1,3}(?:[,\s]\d{2,3})*(?:[.]\d{1,2})"
        r"|\d+(?:[.]\d{1,2})|\d{1,3}(?:[.]\d{3})*(?:[,]\d{1,2}))"
    )
    matches = re.findall(pattern, line)
    results: list[Decimal] = []
    for m in matches:
        clean_token = m.strip()
        try:
            val = parse_money(clean_token)
            results.append(val)
        except ValueError:
            continue
    return results


class TotalExtractor:
    """Extracts total payable amount using anchor scanning and max candidate fallback."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize total extractor with rule definitions."""
        self.rules = (rules or _RULES).get("total", {})
        default_anchors = [
            "grand total",
            "total amount",
            "amount due",
            "net payable",
            "balance due",
            "total due",
            "total",
        ]
        self.anchors = self.rules.get("anchors", default_anchors)

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract total amount."""
        lines = text.splitlines()

        # Phase 1: High-specificity anchors (grand total, amount due, etc.)
        specific_anchors = [a for a in self.anchors if a != "total"]
        for idx, line in enumerate(lines):
            low = line.lower()
            if any(anchor in low for anchor in specific_anchors):
                candidates = _find_money_candidates(line)
                if not candidates and idx + 1 < len(lines):
                    candidates = _find_money_candidates(lines[idx + 1])
                if candidates:
                    conf = 0.9 * (0.9 if is_ocr else 1.0)
                    return FieldResult(value=candidates[-1], confidence=round(conf, 3), span=line)

        # Phase 2: Generic "total" anchor with strict exclusion of subtotal/tax
        excluded_tokens = ("subtotal", "sub total", "tax", "vat", "gst", "qty", "items")
        for idx, line in enumerate(lines):
            low = line.lower()
            if re.search(r"\btotal\b", low):
                if any(x in low for x in excluded_tokens):
                    continue
                candidates = _find_money_candidates(line)
                if not candidates and idx + 1 < len(lines):
                    candidates = _find_money_candidates(lines[idx + 1])
                if candidates:
                    conf = 0.85 * (0.9 if is_ocr else 1.0)
                    return FieldResult(value=candidates[-1], confidence=round(conf, 3), span=line)

        # Fallback: largest valid amount in the document
        all_candidates: list[Decimal] = []
        for line in lines:
            all_candidates.extend(_find_money_candidates(line))

        if all_candidates:
            max_val = max(all_candidates)
            conf = 0.4 * (0.9 if is_ocr else 1.0)
            return FieldResult(value=max_val, confidence=round(conf, 3), span=str(max_val))

        return None


class SubtotalExtractor:
    """Extracts subtotal / net amount before taxes."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize subtotal extractor."""
        self.rules = (rules or _RULES).get("subtotal", {})
        self.anchors = self.rules.get(
            "anchors", ["subtotal", "sub total", "taxable value", "net amount"]
        )

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract subtotal amount."""
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            low = line.lower()
            if any(anchor in low for anchor in self.anchors):
                candidates = _find_money_candidates(line)
                if not candidates and idx + 1 < len(lines):
                    candidates = _find_money_candidates(lines[idx + 1])
                if candidates:
                    conf = 0.9 * (0.9 if is_ocr else 1.0)
                    return FieldResult(value=candidates[-1], confidence=round(conf, 3), span=line)
        return None


class TaxExtractor:
    """Extracts tax amounts including Indian GST splits (CGST, SGST, IGST)."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize tax extractor."""
        self.rules = (rules or _RULES).get("tax", {})
        self.tax_anchors = self.rules.get("anchors", ["tax amount", "total tax", "tax", "vat"])
        self.cgst_anchors = self.rules.get("cgst_anchors", ["cgst", "central gst"])
        self.sgst_anchors = self.rules.get("sgst_anchors", ["sgst", "state gst"])
        self.igst_anchors = self.rules.get("igst_anchors", ["igst", "integrated gst"])

    def _extract_component(
        self, lines: list[str], anchors: list[str], exclude: list[str] | None = None
    ) -> Decimal | None:
        """Extract monetary value matching specific tax component anchors."""
        for idx, line in enumerate(lines):
            low = line.lower()
            if exclude and any(x in low for x in exclude):
                continue
            matched = False
            for a in anchors:
                if len(a) <= 4:
                    if re.search(rf"\b{re.escape(a)}\b", low):
                        matched = True
                        break
                elif a in low:
                    matched = True
                    break
            if matched:
                candidates = _find_money_candidates(line)
                if not candidates and idx + 1 < len(lines):
                    candidates = _find_money_candidates(lines[idx + 1])
                if candidates:
                    return candidates[-1]
        return None

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract tax total and GST breakdown."""
        lines = text.splitlines()
        cgst = self._extract_component(lines, self.cgst_anchors)
        sgst = self._extract_component(lines, self.sgst_anchors)
        igst = self._extract_component(lines, self.igst_anchors)

        tax_total = self._extract_component(
            lines, self.tax_anchors, exclude=["cgst", "sgst", "igst"]
        )
        if tax_total is None and (cgst or sgst or igst):
            cgst_val = cgst or Decimal("0.00")
            sgst_val = sgst or Decimal("0.00")
            igst_val = igst or Decimal("0.00")
            tax_total = cgst_val + sgst_val + igst_val

        if tax_total is not None or cgst or sgst or igst:
            conf = 0.9 * (0.9 if is_ocr else 1.0)
            breakdown = {
                "tax_total": tax_total,
                "cgst": cgst,
                "sgst": sgst,
                "igst": igst,
            }
            return FieldResult(value=breakdown, confidence=round(conf, 3), span=text[:50])

        return None


class InvoiceNumberExtractor:
    """Extracts invoice, bill, or receipt identification numbers."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize invoice number extractor."""
        self.rules = (rules or _RULES).get("invoice_number", {})
        self.pattern = re.compile(
            r"(?i)\b(?:tax\s+invoice|invoice|inv|bill|receipt)"
            r"\s*(?:no\.?|#|na\.?|nar|id|num|number)?\s*[:\s-]*([A-Za-z0-9][A-Za-z0-9\-_/]{1,30})"
        )

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract invoice number string."""
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            match = self.pattern.search(line)
            if match:
                num = match.group(1).strip(" -:#/.")
                if not num and idx + 1 < len(lines):
                    next_m = re.search(r"^\s*([A-Za-z0-9][A-Za-z0-9\-_/]{1,30})", lines[idx + 1])
                    if next_m:
                        num = next_m.group(1).strip(" -:#/.")
                if num and len(num) >= 2:
                    conf = 0.9 * (0.9 if is_ocr else 1.0)
                    return FieldResult(value=num, confidence=round(conf, 3), span=line)

        # Fallback pattern without anchor
        fallback_pat = (
            r"\b([A-Za-z]{2,5}[-/][0-9A-Za-z]{3,15}|INV[-/][0-9]{3,10}|REC[-/][0-9]{3,10})\b"
        )
        match = re.search(fallback_pat, text)
        if match:
            conf = 0.6 * (0.9 if is_ocr else 1.0)
            return FieldResult(
                value=match.group(1),
                confidence=round(conf, 3),
                span=match.group(0),
            )

        return None


class InvoiceDateExtractor:
    """Extracts issuance date with anchor scanning and normalization."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize invoice date extractor."""
        self.rules = (rules or _RULES).get("invoice_date", {})
        default_anchors = [
            "invoice date",
            "bill date",
            "date of issue",
            "receipt date",
            "date",
            "dated",
        ]
        self.anchors = self.rules.get("anchors", default_anchors)

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract and normalize invoice date."""
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            low = line.lower()
            for anchor in self.anchors:
                if anchor in low:
                    pos = low.find(anchor)
                    rest = line[pos + len(anchor) :].strip()
                    if not rest and idx + 1 < len(lines):
                        rest = lines[idx + 1].strip()

                    # Find date tokens: dd/mm/yyyy, yyyy-mm-dd, or named months
                    date_match = re.search(
                        r"[:\s-]*(\d{1,4}[-/.][A-Za-z0-9]{1,9}[-/.][A-Za-z0-9]{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
                        rest,
                    )
                    if date_match:
                        raw_date_str = date_match.group(1).strip()
                        try:
                            d = parse_date(raw_date_str, locale=locale)
                            conf = 0.9 * (0.9 if is_ocr else 1.0)
                            return FieldResult(value=d, confidence=round(conf, 3), span=line)
                        except ValueError:
                            continue

        # Fallback: scan any line for dates
        for line in lines:
            date_match = re.search(
                r"\b(\d{1,2}[-/.][A-Za-z0-9]{1,9}[-/.][A-Za-z0-9]{2,4}|\d{4}[-/.][A-Za-z0-9]{1,9}[-/.][A-Za-z0-9]{1,2})\b",
                line,
            )
            if date_match:
                try:
                    d = parse_date(date_match.group(1), locale=locale)
                    conf = 0.6 * (0.9 if is_ocr else 1.0)
                    return FieldResult(value=d, confidence=round(conf, 3), span=line)
                except ValueError:
                    continue

        return None


class VendorNameExtractor:
    """Extracts vendor name from the top header lines of page 1."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize vendor name extractor."""
        self.rules = (rules or _RULES).get("vendor_name", {})
        self.max_lines = self.rules.get("max_header_lines", 8)
        self.skip_keywords = self.rules.get(
            "skip_keywords",
            [
                "tax invoice",
                "invoice",
                "bill to",
                "ship to",
                "customer",
                "date",
                "total",
                "subtotal",
                "gstin",
                "tax id",
                "tax",
                "vat",
                "phone",
                "tel",
                "email",
                "address",
                "cin",
                "pan",
                "original for recipient",
            ],
        )

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract vendor name."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines[: self.max_lines]:
            low = line.lower()
            should_skip = False
            for k in self.skip_keywords:
                if re.search(rf"\b{re.escape(k)}\b", low):
                    should_skip = True
                    break
            if should_skip:
                continue

            if re.match(r"^[\d\W]+$", line) or re.search(r"^(?:tax|vat|gst|cin|pan)\b", low):
                continue
            if len(line) >= 3 and len(line) <= 60:
                conf = 0.9 * (0.9 if is_ocr else 1.0)
                return FieldResult(value=line, confidence=round(conf, 3), span=line)

        return None


class VendorTaxIdExtractor:
    """Extracts vendor tax identifiers (Indian GSTIN, VAT)."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize tax ID extractor."""
        self.rules = (rules or _RULES).get("vendor_tax_id", {})
        self.gstin_pattern = self.rules.get(
            "gstin_pattern", r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"
        )
        self.vat_pattern = self.rules.get("vat_pattern", r"\b[A-Z]{2}[0-9A-Z]{8,12}\b")

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract GSTIN or VAT identifier."""
        # 1. Indian GSTIN
        gstin_match = re.search(self.gstin_pattern, text)
        if gstin_match:
            conf = 0.9 * (0.9 if is_ocr else 1.0)
            gstin_val = gstin_match.group(0)
            return FieldResult(value=gstin_val, confidence=round(conf, 3), span=gstin_val)

        # 2. Anchored Tax ID or VAT ID
        tax_id_match = re.search(
            r"(?i)(?:tax\s*id|vat\s*id|vat\s*no|vat)\s*[:#]?\s*([A-Za-z0-9-]{8,16})\b",
            text,
        )
        if tax_id_match:
            conf = 0.9 * (0.9 if is_ocr else 1.0)
            return FieldResult(
                value=tax_id_match.group(1),
                confidence=round(conf, 3),
                span=tax_id_match.group(0),
            )

        # 3. European VAT unanchored pattern (2 country letters + 7-13 alphanumeric with digits)
        vat_match = re.search(r"\b([A-Z]{2}[0-9A-Z]*[0-9]{2,}[0-9A-Z]*)\b", text)
        if vat_match and len(vat_match.group(1)) >= 9:
            conf = 0.7 * (0.9 if is_ocr else 1.0)
            return FieldResult(
                value=vat_match.group(1),
                confidence=round(conf, 3),
                span=vat_match.group(0),
            )

        return None


class CurrencyExtractor:
    """Extracts currency ISO code from symbols or currency mentions."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize currency extractor."""
        self.rules = (rules or _RULES).get("currency", {})
        default_map = {
            "₹": "INR",
            "rs": "INR",
            "inr": "INR",
            "$": "USD",
            "usd": "USD",
            "€": "EUR",
            "eur": "EUR",
            "£": "GBP",
            "gbp": "GBP",
        }
        self.symbol_map = self.rules.get("symbol_map", default_map)
        self.default_currency = self.rules.get("default_currency", "INR")

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult:
        """Extract currency ISO code."""
        low = text.lower()
        for token, code in self.symbol_map.items():
            if token in low:
                conf = 0.9 * (0.9 if is_ocr else 1.0)
                return FieldResult(value=code, confidence=round(conf, 3), span=token)

        if locale == "US":
            default_code = "USD"
        elif locale == "EU":
            default_code = "EUR"
        else:
            default_code = self.default_currency
        return FieldResult(value=default_code, confidence=0.5, span="default")


class InvoiceFieldsExtractor:
    """Coordinating extractor running all modular field extractors on a TextResult."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        """Initialize field extractors with rules."""
        active_rules = rules or _RULES
        self.total_extractor = TotalExtractor(active_rules)
        self.subtotal_extractor = SubtotalExtractor(active_rules)
        self.tax_extractor = TaxExtractor(active_rules)
        self.invoice_number_extractor = InvoiceNumberExtractor(active_rules)
        self.date_extractor = InvoiceDateExtractor(active_rules)
        self.vendor_extractor = VendorNameExtractor(active_rules)
        self.tax_id_extractor = VendorTaxIdExtractor(active_rules)
        self.currency_extractor = CurrencyExtractor(active_rules)

    def extract_fields(self, text_result: TextResult, locale: str = "IN") -> ExtractedInvoice:
        """Extract all invoice fields and produce a validated ExtractedInvoice model."""
        text = text_result.raw_text
        layout = text_result.words
        is_ocr = text_result.method == "tesseract_ocr"

        total_res = self.total_extractor.extract(text, layout, is_ocr, locale)
        subtotal_res = self.subtotal_extractor.extract(text, layout, is_ocr, locale)
        tax_res = self.tax_extractor.extract(text, layout, is_ocr, locale)
        inv_num_res = self.invoice_number_extractor.extract(text, layout, is_ocr, locale)
        date_res = self.date_extractor.extract(text, layout, is_ocr, locale)
        vendor_res = self.vendor_extractor.extract(text, layout, is_ocr, locale)
        tax_id_res = self.tax_id_extractor.extract(text, layout, is_ocr, locale)
        currency_res = self.currency_extractor.extract(text, layout, is_ocr, locale)

        confidence_map: dict[str, float] = {}
        if total_res:
            confidence_map["total"] = total_res.confidence
        if subtotal_res:
            confidence_map["subtotal"] = subtotal_res.confidence
        if tax_res:
            confidence_map["tax_total"] = tax_res.confidence
        if inv_num_res:
            confidence_map["invoice_number"] = inv_num_res.confidence
        if date_res:
            confidence_map["invoice_date"] = date_res.confidence
        if vendor_res:
            confidence_map["vendor_name"] = vendor_res.confidence
        if tax_id_res:
            confidence_map["vendor_tax_id"] = tax_id_res.confidence
        if currency_res:
            confidence_map["currency"] = currency_res.confidence

        tax_breakdown = tax_res.value if tax_res else {}
        if total_res and total_res.value > Decimal("0.00"):
            total_val = total_res.value
        else:
            total_val = Decimal("0.01")
        vendor_val = vendor_res.value if vendor_res else "Unknown Vendor"

        key_confs = [
            confidence_map.get("total", 0.4),
            confidence_map.get("invoice_date", 0.4),
            confidence_map.get("vendor_name", 0.4),
        ]
        overall_conf = round(sum(key_confs) / len(key_confs), 3)

        return ExtractedInvoice(
            vendor_name=str(vendor_val),
            vendor_tax_id=tax_id_res.value if tax_id_res else None,
            invoice_number=inv_num_res.value if inv_num_res else None,
            invoice_date=date_res.value if date_res else None,
            currency=currency_res.value,
            subtotal=subtotal_res.value if subtotal_res else None,
            tax_total=tax_breakdown.get("tax_total"),
            cgst=tax_breakdown.get("cgst"),
            sgst=tax_breakdown.get("sgst"),
            igst=tax_breakdown.get("igst"),
            total=total_val,
            confidence=confidence_map,
            overall_confidence=overall_conf,
        )
