"""Tests for date parsing and normalization."""

from datetime import date

import pytest

from invoiceflow.utils.dates import parse_date


def test_iso_date_format() -> None:
    """Parse standard ISO yyyy-mm-dd date format."""
    assert parse_date("2024-05-12") == date(2024, 5, 12)
    assert parse_date("2023-12-31") == date(2023, 12, 31)


def test_indian_date_formats() -> None:
    """Parse common Indian date formats (dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy)."""
    assert parse_date("12/05/2024", locale="IN") == date(2024, 5, 12)
    assert parse_date("25-10-2023", locale="IN") == date(2023, 10, 25)
    assert parse_date("31.01.2022", locale="IN") == date(2022, 1, 31)


def test_named_month_formats() -> None:
    """Parse alphanumeric dates with full and abbreviated month names."""
    assert parse_date("15-Jan-2024") == date(2024, 1, 15)
    assert parse_date("15-OCT-2023") == date(2023, 10, 15)
    assert parse_date("15 January 2024") == date(2024, 1, 15)
    assert parse_date("Jan 15, 2024") == date(2024, 1, 15)
    assert parse_date("31-Aug-2022") == date(2022, 8, 31)


def test_locale_ambiguity_resolution() -> None:
    """Resolve day/month ambiguity using the specified locale."""
    # 03/04/2024 -> 3rd April in IN, 4th March in US
    assert parse_date("03/04/2024", locale="IN") == date(2024, 4, 3)
    assert parse_date("03/04/2024", locale="US") == date(2024, 3, 4)


def test_date_sanity_checks() -> None:
    """Reject dates before year 2000 and dates in the future."""
    with pytest.raises(ValueError, match="before year 2000"):
        parse_date("1999-12-31")
    with pytest.raises(ValueError, match="before year 2000"):
        parse_date("01/01/1990")

    future_date = date.today().year + 2
    with pytest.raises(ValueError, match="future"):
        parse_date(f"{future_date}-01-01")


def test_invalid_date_strings() -> None:
    """Reject empty strings or unparseable text."""
    with pytest.raises(ValueError):
        parse_date("")
    with pytest.raises(ValueError):
        parse_date("invalid-date")
    with pytest.raises(ValueError):
        parse_date("32/01/2024")
