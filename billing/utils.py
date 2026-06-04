"""Shared utilities for the billing app."""
from decimal import Decimal, ROUND_HALF_UP


def money(value):
    """Standardizes decimal rounding to 2 decimal places."""
    if value is None:
        return Decimal("0.00")
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
