"""Date parsing, normalization, and validation utilities."""

from datetime import date

from dateutil import parser


def _validate_date_sanity(parsed_date: date) -> None:
    """Validate that parsed date is between 2000-01-01 and today."""
    if parsed_date.year < 2000:
        raise ValueError(f"Date {parsed_date} is before year 2000")
    if parsed_date > date.today():
        raise ValueError(f"Date {parsed_date} is in the future")


def parse_date(raw_value: str, locale: str = "IN") -> date:
    """Parse date string into timezone-naive date with locale ambiguity and sanity checks."""
    if not raw_value or not raw_value.strip():
        raise ValueError("Date string is empty")

    cleaned = raw_value.strip()

    # Handle ISO YYYY-MM-DD or YYYY/MM/DD before applying dayfirst heuristic
    try:
        dt_iso = date.fromisoformat(cleaned.replace("/", "-"))
        _validate_date_sanity(dt_iso)
        return dt_iso
    except (ValueError, TypeError):
        pass

    day_first = locale.upper() == "IN"
    try:
        dt = parser.parse(cleaned, dayfirst=day_first, fuzzy=False)
    except (parser.ParserError, OverflowError, ValueError) as err:
        raise ValueError(f"Cannot parse date string: {raw_value!r}") from err

    result_date = dt.date()
    _validate_date_sanity(result_date)
    return result_date
