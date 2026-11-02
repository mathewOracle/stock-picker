"""Series for the daily candlestick + indicator charts, shared by the stock and the coin deep-dive pages.

A report only needs `.plan` (entry/stop/targets) and `.chart.levels` (support/resistance), so stocks and coins
draw through one function.
"""

import math

from app import data
from app.indicators import compute_indicators
from app.prices import chart_precision, round_price

CHART_LEVELS_EACH_SIDE = 3  # more S/R lines than this just clutters the chart


def chart_levels(report) -> list[dict]:
    price = report.metrics["price"]
    strong = [lv for lv in report.chart.levels if lv.touches >= 2]
    below = [lv for lv in strong if lv.price < price][-CHART_LEVELS_EACH_SIDE:]
    above = [lv for lv in strong if lv.price >= price][:CHART_LEVELS_EACH_SIDE]
    return [{"price": lv.price, "title": lv.label or f"S/R x{lv.touches}"} for lv in below + above]


def chart_payload(symbol: str, report) -> dict:
    ind = compute_indicators(data.load_ohlcv(symbol)).tail(250)
    times = [d.strftime("%Y-%m-%d") for d in ind.index]

    def line(col: str) -> list[dict]:
        return [{"time": t, "value": round_price(float(v))} for t, v in zip(times, ind[col]) if math.isfinite(v)]

    return {
        "candles": [{"time": t, "open": r.Open, "high": r.High, "low": r.Low, "close": r.Close}
                    for t, r in zip(times, ind.itertuples())],
        "volume": [{"time": t, "value": float(r.Volume), "color": "#16a34a80" if r.Close >= r.Open else "#dc262680"}
                   for t, r in zip(times, ind.itertuples())],
        **{col: line(col) for col in ("ema20", "sma50", "sma200", "bb_upper", "bb_lower", "st_line",
                                      "rsi", "macd", "macd_signal", "macd_hist")},
        "levels": chart_levels(report),
        "plan": {"entry": report.plan.entry, "stop": report.plan.stop,
                 "target1": report.plan.target1, "target2": report.plan.target2},
        "precision": chart_precision(report.metrics["price"]),   # the price axis: 2 decimals, more for sub-$1 coins
    }
