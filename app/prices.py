"""Price precision for every market: Rs 2,500.45, $1.2534 (XRP), $0.0752 (DOGE) and $0.00000462 (SHIB) must all survive.

One rule: at least `digits` decimals, more when that is what it takes to keep `sig` significant figures. A fixed
two decimals turns XRP's $1.2534 into a 1% staircase and SHIB into 0.00. With the readings' defaults (1 decimal,
2 significant figures) every price >= 1 formats exactly as it always did, so stock signal texts never change.
"""

import math


def _decimals(value: float, digits: int, sig: int) -> int:
    """`digits` decimals, or more if that is what it takes to show `sig` significant figures."""
    if not math.isfinite(value) or value == 0:
        return digits
    return max(digits, sig - 1 - math.floor(math.log10(abs(value))))


def round_price(value: float, sig: int = 6) -> float:
    """For storage and charts: 6 significant figures, never fewer than 2 decimals."""
    return round(value, _decimals(value, 2, sig))


def price_text(value: float, digits: int = 1, sig: int = 2, signed: bool = False, grouped: bool = True) -> str:
    """For signal readings: '2,500.5' as before; '0.075' or '0.0000046' instead of '0.0' for tiny prices."""
    return f"{value:{'+' if signed else ''}{',' if grouped else ''}.{_decimals(value, digits, sig)}f}"


def chart_precision(price: float) -> int:
    """Decimals for a chart's price axis: 2 for ordinary prices, enough for 4 significant figures on small ones."""
    return _decimals(price, 2, 4)
