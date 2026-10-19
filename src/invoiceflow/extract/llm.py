"""LLM fallback extraction with schema enforcement and cost logging."""

import json
import re
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel

from invoiceflow.extract.text import WordBox
from invoiceflow.models import ExtractedInvoice, FieldResult
from invoiceflow.utils.dates import parse_date
from invoiceflow.utils.logging import get_logger
from invoiceflow.utils.money import parse_money

logger = get_logger(__name__)

INVOICE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string", "description": "Legal business or vendor name"},
        "vendor_tax_id": {
            "type": ["string", "null"],
            "description": "Tax ID / GSTIN / EIN / VAT number",
        },
        "invoice_number": {
            "type": ["string", "null"],
            "description": "Unique invoice identifier/number",
        },
        "invoice_date": {
            "type": ["string", "null"],
            "description": "Date of invoice in YYYY-MM-DD format",
        },
        "currency": {"type": "string", "description": "3-letter ISO currency code (e.g. INR, USD)"},
        "subtotal": {
            "type": ["number", "string", "null"],
            "description": "Net subtotal before tax",
        },
        "tax_total": {
            "type": ["number", "string", "null"],
            "description": "Total tax amount",
        },
        "cgst": {"type": ["number", "string", "null"], "description": "Central GST"},
        "sgst": {"type": ["number", "string", "null"], "description": "State GST"},
        "igst": {"type": ["number", "string", "null"], "description": "Integrated GST"},
        "total": {"type": ["number", "string"], "description": "Final payable grand total"},
    },
    "required": ["vendor_name", "total"],
}


class LLMResponse(BaseModel):
    """Container for raw LLM text completion and associated token/cost metadata."""

    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: Decimal = Decimal("0.0000")
    model: str = "default"


class LLMClient(Protocol):
    """Protocol defining the provider-agnostic interface for LLM completions."""

    def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> LLMResponse:
        """Execute a text completion request with timeout and optional JSON schema."""
        ...


class FakeLLMClient:
    """Mock LLM client for testing extraction fallback and error handling."""

    def __init__(
        self,
        default_response: dict[str, Any] | str | None = None,
        responses: list[dict[str, Any] | str] | None = None,
        prompt_tokens: int = 200,
        completion_tokens: int = 50,
        cost: Decimal = Decimal("0.0002"),
        model: str = "fake-model",
        should_timeout: bool = False,
        should_fail: bool = False,
        error_message: str = "Simulated provider error",
    ) -> None:
        """Initialize mock LLM client with predictable responses and simulated errors."""
        self.default_response = default_response or {
            "vendor_name": "Fallback Vendor Ltd",
            "invoice_number": "INV-FALLBACK-01",
            "invoice_date": "2026-03-15",
            "currency": "INR",
            "subtotal": "1000.00",
            "tax_total": "180.00",
            "cgst": "90.00",
            "sgst": "90.00",
            "igst": None,
            "total": "1180.00",
        }
        self.responses = list(responses) if responses is not None else []
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost = cost
        self.model = model
        self.should_timeout = should_timeout
        self.should_fail = should_fail
        self.error_message = error_message
        self.call_count = 0
        self.recorded_prompts: list[str] = []

    def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> LLMResponse:
        """Return the next configured fake response or raise configured exceptions."""
        self.call_count += 1
        self.recorded_prompts.append(prompt)

        if self.should_timeout:
            raise TimeoutError("Simulated LLM call timeout")
        if self.should_fail:
            raise RuntimeError(self.error_message)

        if self.responses:
            item = self.responses.pop(0)
            content_str = item if isinstance(item, str) else json.dumps(item)
        elif isinstance(self.default_response, str):
            content_str = self.default_response
        else:
            content_str = json.dumps(self.default_response)

        return LLMResponse(
            content=content_str,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_cost=self.cost,
            model=self.model,
        )


class LLMExtractor:
    """LLM fallback extractor conforming to the FieldExtractor protocol."""

    def __init__(
        self,
        client: LLMClient,
        timeout: float = 30.0,
        model: str = "gpt-4o-mini",
        cost_per_1k_input: Decimal = Decimal("0.00015"),
        cost_per_1k_output: Decimal = Decimal("0.0006"),
    ) -> None:
        """Initialize LLM extractor with client and cost tracking parameters."""
        self.client = client
        self.timeout = timeout
        self.model = model
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output

    def _build_prompt(self, text: str, locale: str) -> str:
        """Construct structured prompt including JSON schema and raw invoice text."""
        schema_json = json.dumps(INVOICE_JSON_SCHEMA, indent=2)
        return (
            f"You are an expert invoice and receipt data extraction system.\n"
            f"Extract all invoice metadata from the text below using locale '{locale}'.\n"
            f"Return ONLY valid JSON matching this schema:\n{schema_json}\n\n"
            f"Document Text:\n{text}\n"
        )

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        """Calculate estimated total USD cost from token counts."""
        input_cost = (Decimal(prompt_tokens) * self.cost_per_1k_input) / Decimal("1000")
        output_cost = (Decimal(completion_tokens) * self.cost_per_1k_output) / Decimal("1000")
        return round(input_cost + output_cost, 6)

    def _parse_money_val(self, val: Any) -> Decimal | None:
        """Safely parse arbitrary money value from LLM response into Decimal."""
        if val is None:
            return None
        try:
            return parse_money(str(val))
        except (ValueError, TypeError):
            return None

    def _parse_date_val(self, val: Any, locale: str) -> date | None:
        """Safely parse invoice date from LLM response into date object."""
        if not val:
            return None
        try:
            return parse_date(str(val), locale=locale)
        except (ValueError, TypeError):
            return None

    def _clean_json_content(self, raw_content: str) -> str:
        """Strip markdown code fence blocks if present."""
        clean = raw_content.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        return clean.strip()

    def _build_invoice_from_dict(
        self, data: dict[str, Any], locale: str = "IN"
    ) -> ExtractedInvoice:
        """Construct validated ExtractedInvoice model from raw JSON dictionary."""
        total_val = self._parse_money_val(data.get("total")) or Decimal("0.01")
        subtotal_val = self._parse_money_val(data.get("subtotal"))
        tax_total_val = self._parse_money_val(data.get("tax_total"))
        cgst_val = self._parse_money_val(data.get("cgst"))
        sgst_val = self._parse_money_val(data.get("sgst"))
        igst_val = self._parse_money_val(data.get("igst"))

        vendor_name = str(data.get("vendor_name") or "Unknown Vendor").strip()
        inv_num = str(data["invoice_number"]).strip() if data.get("invoice_number") else None
        inv_date = self._parse_date_val(data.get("invoice_date"), locale)
        currency_raw = str(data.get("currency") or "INR").upper().strip()
        currency = currency_raw if re.match(r"^[A-Z]{3}$", currency_raw) else "INR"

        conf_map = {
            "vendor_name": 0.85,
            "total": 0.85,
            "invoice_number": 0.85 if inv_num else 0.0,
            "invoice_date": 0.85 if inv_date else 0.0,
            "currency": 0.85,
        }

        return ExtractedInvoice(
            vendor_name=vendor_name,
            vendor_tax_id=str(data["vendor_tax_id"]).strip() if data.get("vendor_tax_id") else None,
            invoice_number=inv_num,
            invoice_date=inv_date,
            currency=currency,
            subtotal=subtotal_val,
            tax_total=tax_total_val,
            cgst=cgst_val,
            sgst=sgst_val,
            igst=igst_val,
            total=total_val,
            confidence=conf_map,
            overall_confidence=0.85,
        )

    def extract(
        self,
        text: str,
        layout: list[WordBox] | None = None,
        is_ocr: bool = False,
        locale: str = "IN",
    ) -> FieldResult | None:
        """Extract invoice data using LLM completion conforming to FieldExtractor protocol."""
        prompt = self._build_prompt(text, locale)
        try:
            resp = self.client.complete(
                prompt=prompt,
                schema=INVOICE_JSON_SCHEMA,
                timeout=self.timeout,
            )
        except Exception as exc:
            logger.warning(
                "LLM extraction request failed or timed out: %s",
                exc,
                extra={"stage": "llm_fallback"},
            )
            return None

        cost = resp.total_cost or self._calculate_cost(resp.prompt_tokens, resp.completion_tokens)
        logger.info(
            "LLM extraction completed successfully",
            extra={
                "stage": "llm_fallback",
                "model": resp.model or self.model,
                "tokens": resp.prompt_tokens + resp.completion_tokens,
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
                "cost_usd": float(cost),
            },
        )

        try:
            clean_json = self._clean_json_content(resp.content)
            data: dict[str, Any] = json.loads(clean_json)
            invoice = self._build_invoice_from_dict(data, locale)
            return FieldResult(value=invoice, confidence=invoice.overall_confidence, span="llm")
        except Exception as parse_exc:
            logger.warning(
                "Failed to parse LLM JSON response: %s",
                parse_exc,
                extra={"stage": "llm_fallback"},
            )
            return None

    def extract_invoice(self, text: str, locale: str = "IN") -> ExtractedInvoice | None:
        """Direct helper returning ExtractedInvoice domain model or None on failure."""
        res = self.extract(text=text, locale=locale)
        if res and isinstance(res.value, ExtractedInvoice):
            return res.value
        return None
