"""One place for how money and dates are shown, so the API, the assistant and the UI agree."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal


def money(value: Decimal | float | int) -> str:
    return f"${Decimal(value).quantize(Decimal('0.01'), ROUND_HALF_UP):,.2f}"


def to_cents(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def day(value: datetime) -> str:
    """Unambiguous date in UTC, e.g. "Oct 11, 2026"."""
    return f"{value:%b} {value.day}, {value.year}"
