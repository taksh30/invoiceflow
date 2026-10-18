"""Currency and monetary decimal parsing utilities."""

import re
from decimal import Decimal, InvalidOperation

_CURRENCY_SYMBOLS = ["₹", "rs.", "rs", "inr", "$", "usd", "€", "eur", "£", "gbp"]
_OCR_TRANSLATION = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "s": "5"})


def _strip_currency(text: str) -> str:
    """Remove currency symbols, abbreviations, and extraneous whitespace."""
    cleaned = text.strip()
    lower_cleaned = cleaned.lower()
    for sym in _CURRENCY_SYMBOLS:
        if lower_cleaned.startswith(sym):
            cleaned = cleaned[len(sym) :].strip()
            lower_cleaned = cleaned.lower()
        if lower_cleaned.endswith(sym):
            cleaned = cleaned[: -len(sym)].strip()
            lower_cleaned = cleaned.lower()
    return cleaned


def _apply_ocr_fixes(text: str) -> str:
    """Correct character recognition misreadings in numeric tokens."""
    return text.translate(_OCR_TRANSLATION)


def _normalize_separators(text: str) -> str:
    """Normalize thousand and decimal separators across US, Indian, and EU formats."""
    last_dot = text.rfind(".")
    last_comma = text.rfind(",")

    if last_dot != -1 and last_comma != -1:
        if last_comma > last_dot:
            # European format: 1.234,56 -> 1234.56
            return text.replace(".", "").replace(",", ".")
        # Standard/Indian format: 1,23,456.78 -> 123456.78
        return text.replace(",", "")

    if last_comma != -1:
        decimals = len(text) - last_comma - 1
        if text.count(",") == 1 and decimals in (1, 2):
            return text.replace(",", ".")
        return text.replace(",", "")

    return text


def parse_money(raw_value: str) -> Decimal:
    """Parse monetary string to Decimal, validating positive amount and max 2 decimals."""
    if not raw_value or not raw_value.strip():
        raise ValueError("Amount string is empty")

    cleaned = _strip_currency(raw_value)
    if not cleaned:
        raise ValueError("Amount contains no numeric content")

    if cleaned.startswith("-"):
        raise ValueError("Amount must be positive")

    cleaned = _apply_ocr_fixes(cleaned)
    normalized = _normalize_separators(cleaned)

    if not re.match(r"^\d+(\.\d+)?$", normalized):
        raise ValueError(f"Invalid monetary format: {raw_value!r}")

    if "." in normalized:
        decimal_places = len(normalized.split(".")[1])
        if decimal_places > 2:
            raise ValueError(f"Amount has more than 2 decimal places: {raw_value!r}")

    try:
        amount = Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation as err:
        raise ValueError(f"Cannot convert to Decimal: {raw_value!r}") from err

    if amount <= Decimal("0.00"):
        raise ValueError("Amount must be positive")

    return amount
