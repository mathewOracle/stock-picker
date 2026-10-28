"""Market overview: index cards, chart series and market internals, from what the daily refresh already stored.

No FastAPI and no HTML in here (same split as deskview.py), so the rules are unit-testable. Everything is per
market: the active profile's INDICES and tracked stocks, so India and US never show each other's numbers.
"""

import math
from collections import defaultdict

from app import data
from app.universe import BENCHMARK, INDICES, VIX

SERIES_SESSIONS = 504   # ~2 years: a 200-day average plus the longest range button (2Y)
MIN_SESSIONS = 30       # fewer closes than this is not a chart (same bar as the cards in analysis._indices)


def kind(symbol: str) -> str:
    """How a line behaves in the charts: 'index' compares rebased, 'vol' (VIX) and 'fx' stand alone."""
    return "vol" if symbol == VIX else "fx" if symbol.endswith("=X") else "index"


def cards(indices: list[dict]) -> list[dict]:
    """The metric cards: analysis' index numbers plus how each line charts. Indices first, then volatility, then currency."""
    order = {"index": 0, "vol": 1, "fx": 2}
    tagged = [{**i, "kind": kind(i["symbol"])} for i in indices]
    return sorted(tagged, key=lambda card: order[card["kind"]])   # stable: profile order kept inside each kind


def series() -> list[dict]:
    """Close series per index for the browser: {symbol, name, kind, t: [YYYY-MM-DD], v: [close]}."""
    out = []
    for symbol, name in INDICES.items():
        frame = data.load_ohlcv(symbol)
        if frame is None:
            continue
        close = frame["Close"].dropna().tail(SERIES_SESSIONS)
        if len(close) > MIN_SESSIONS:
            out.append({"symbol": symbol, "name": name, "kind": kind(symbol),
                        "t": [day.strftime("%Y-%m-%d") for day in close.index], "v": [round(float(v), 4) for v in close]})
    return out


def _finite(values) -> list[float]:
    return [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]


def internals(reports: list, breadth: float | None) -> dict:
    """What the tracked stocks say about the market today: advancers vs decliners, breadth, sector returns.

    breadth = share of stocks above their 200-day average (from the analysis, None when unknown).
    Sectors are sorted best 1-day first; `bar` is the 1-day return as a share of the largest move (0-100).
    """
    day = _finite(r.metrics["ret_1d"] for r in reports)
    advancers, decliners = sum(v > 0 for v in day), sum(v < 0 for v in day)
    by_sector: dict[str, list] = defaultdict(list)
    for r in reports:
        by_sector[r.metrics["sector"]].append(r.metrics)
    rows = []
    for name, group in by_sector.items():
        one_day, one_month = _finite(m["ret_1d"] for m in group), _finite(m["ret_1m"] for m in group)
        if one_day:
            rows.append({"name": name, "n": len(group), "ret_1d": sum(one_day) / len(one_day),
                         "ret_1m": sum(one_month) / len(one_month) if one_month else float("nan")})
    rows.sort(key=lambda row: -row["ret_1d"])
    biggest = max((abs(row["ret_1d"]) for row in rows), default=0.0) or 1.0
    for row in rows:
        row["bar"] = abs(row["ret_1d"]) / biggest * 100
    return {"advancers": advancers, "decliners": decliners, "unchanged": len(day) - advancers - decliners,
            "tracked": len(day), "breadth": breadth, "sectors": rows}


def page(analysis_result) -> dict:
    """Everything the market overview panel needs, from one analysis result."""
    return {"cards": cards(analysis_result.indices), "series": series(), "selected": BENCHMARK,
            "internals": internals(analysis_result.reports, analysis_result.breadth_200dma)}
