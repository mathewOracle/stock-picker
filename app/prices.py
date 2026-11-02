"""Price precision for every market: Rs 2,500.45, $0.0752 (DOGE) and $0.00000462 (SHIB) must all survive.

Two decimals are plenty at or above 1. Below 1, a fixed number of decimals erases the price, so small values keep
significant figures instead. Anything >= 1 is formatted exactly as before, so stock output never changes.
"""

import math


def _decimals(value: float, digits: int, sig: int) -> int:
    """`digits` decimals, or more if that is what it takes to show `sig` significant figures of a value below 1."""
    if not math.isfinite(value) or value == 0 or abs(value) >= 1:
        return digits
    return max(digits, sig - 1 - math.floor(math.log10(abs(value))))


def round_price(value: float, sig: int = 6) -> float:
    """For storage and charts: 2 decimals at or above 1, else `sig` significant figures."""
    return round(value, _decimals(value, 2, sig))


def price_text(value: float, digits: int = 1, sig: int = 2, signed: bool = False, grouped: bool = True) -> str:
    """For signal readings: '2,500.5' as before; '0.075' or '0.0000046' instead of '0.0' for tiny prices."""
    return f"{value:{'+' if signed else ''}{',' if grouped else ''}.{_decimals(value, digits, sig)}f}"


def chart_precision(price: float) -> int:
    """Decimals for a chart's price axis: 2 for ordinary prices, enough for 4 significant figures below 1."""
    return _decimals(price, 2, 4)
