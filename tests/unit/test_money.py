"""Tests for currency and decimal amount parsing."""

from decimal import Decimal

import pytest

from invoiceflow.utils.money import parse_money


def test_standard_us_number() -> None:
    """Parse standard decimal amounts with commas."""
    assert parse_money("1,234.56") == Decimal("1234.56")
    assert parse_money("1234.56") == Decimal("1234.56")
    assert parse_money("100") == Decimal("100.00")
    assert parse_money("0.50") == Decimal("0.50")


def test_indian_grouping() -> None:
    """Parse Indian numbering system format (lakhs, crores)."""
    assert parse_money("1,23,456.78") == Decimal("123456.78")
    assert parse_money("99,99,999.00") == Decimal("9999999.00")
    assert parse_money("50,000.50") == Decimal("50000.50")
    assert parse_money("12,34,56,789.10") == Decimal("123456789.10")


def test_european_format() -> None:
    """Parse European numbers using dot as thousands separator and comma as decimal."""
    assert parse_money("1.234,56") == Decimal("1234.56")
    assert parse_money("12.345,67") == Decimal("12345.67")
    assert parse_money("999,99") == Decimal("999.99")


def test_currency_symbols_and_prefixes() -> None:
    """Parse amounts with various currency symbols, codes, and whitespace."""
    assert parse_money("₹ 1,500.50") == Decimal("1500.50")
    assert parse_money("Rs. 2,450.00") == Decimal("2450.00")
    assert parse_money("INR 9,999.99") == Decimal("9999.99")
    assert parse_money("$1,234.56") == Decimal("1234.56")
    assert parse_money("USD 50.00") == Decimal("50.00")
    assert parse_money("€ 1.250,50") == Decimal("1250.50")
    assert parse_money("EUR 99,00") == Decimal("99.00")
    assert parse_money("£ 45.20") == Decimal("45.20")
    assert parse_money("GBP 100.00") == Decimal("100.00")


def test_ocr_cleanup() -> None:
    """Correct common OCR letter/digit misrecognitions in numeric tokens."""
    assert parse_money("1O.5O") == Decimal("10.50")
    assert parse_money("l23.45") == Decimal("123.45")
    assert parse_money("S0.00") == Decimal("50.00")
    assert parse_money("1,OOO.OO") == Decimal("1000.00")


def test_reject_more_than_two_decimals() -> None:
    """Reject numbers with more than 2 decimal places."""
    with pytest.raises(ValueError, match="more than 2 decimal places"):
        parse_money("12.345")
    with pytest.raises(ValueError, match="more than 2 decimal places"):
        parse_money("1.234,567")


def test_reject_negative_or_zero() -> None:
    """Reject negative amounts."""
    with pytest.raises(ValueError, match="must be positive"):
        parse_money("-150.00")
    with pytest.raises(ValueError, match="must be positive"):
        parse_money("-1,250.50")


def test_reject_invalid_strings() -> None:
    """Reject empty, whitespace, or non-numeric strings."""
    with pytest.raises(ValueError):
        parse_money("")
    with pytest.raises(ValueError):
        parse_money("   ")
    with pytest.raises(ValueError):
        parse_money("not-a-number")
    with pytest.raises(ValueError):
        parse_money("12.34.56.78")
