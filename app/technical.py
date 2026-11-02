"""Technical analysis pillar: trend, momentum, volatility, volume and relative strength.

Each `_check_*` function looks at the indicator frame and returns a Signal (or
None if it has nothing to say). Add a check = add a function to CHECKS.
"""

import math

import numpy as np
import pandas as pd

from app.market import MARKET
from app.market.profile import Market, Spans
from app.prices import price_text
from app.signals import Signal, grade

NAN = float("nan")
EXTENDED_ATR = 3.0  # more than this many ATRs above the 20-EMA = chasing
INDEX = MARKET.benchmark_name
RS_SIGNAL = f"Relative strength vs {INDEX}"   # also a pinned model column (research/features.py): one source
SPANS = MARKET.spans   # daily bars per month / quarter / half / year: 21/63/126/252 on an exchange, 30/91/182/365 for crypto


def _ok(*values) -> bool:
    return all(v is not None and math.isfinite(v) for v in values)


def _ret(close: pd.Series, days: int) -> float:
    return float(close.iloc[-1] / close.iloc[-1 - days] - 1) if len(close) > days else NAN


def _bars_since_cross(diff: pd.Series, lookback: int) -> int | None:
    """How many bars ago did `diff` change sign (within lookback)? None if it didn't."""
    signs = np.sign(diff.dropna().tail(lookback + 1).to_numpy())
    for back in range(1, len(signs)):
        if signs[-back] != signs[-back - 1]:
            return back - 1
    return None


def beta(close: pd.Series, benchmark: pd.Series | None, days: int = SPANS.year) -> float:
    """Sensitivity to the index from aligned daily returns (1.0 = moves with the benchmark)."""
    if benchmark is None:
        return NAN
    returns = pd.concat([close.pct_change(), benchmark.pct_change()], axis=1, join="inner").dropna().tail(days)
    if len(returns) < 60:
        return NAN
    stock, index = returns.iloc[:, 0], returns.iloc[:, 1]
    return float(stock.cov(index) / index.var())


def traded_value(df: pd.DataFrame, days: int = 20, market: Market = MARKET) -> float:
    """Average daily traded value in the market's big unit (Rs crore, $ million) -- the liquidity yardstick.

    Stock volume is shares (so value = close x volume); Yahoo's crypto volume is already dollars.
    """
    value = df["Volume"] if market.volume_in_money else df["Close"] * df["Volume"]
    return float(value.tail(days).mean() / market.money.big_divisor)


def price_metrics(close: pd.Series, year: int = SPANS.year) -> dict:
    """Headline return/trend/risk numbers from a close series (stocks and indices).

    `year` is bars per year for THIS series: a weekday index shown next to 24/7 coins still has 252.
    """
    last = float(close.iloc[-1])
    sma200 = close.tail(200).mean() if len(close) >= 200 else NAN
    spans = Spans(year)
    window = close.tail(year)
    daily = close.pct_change().dropna().tail(year)
    return {
        "price": last,
        "ret_1d": _ret(close, 1), "ret_1m": _ret(close, spans.month), "ret_3m": _ret(close, spans.quarter),
        "ret_6m": _ret(close, spans.half), "ret_12m": _ret(close, year),
        "pct_vs_200dma": float(last / sma200 - 1) if _ok(sma200) else NAN,
        "off_high": float(last / window.max() - 1),
        "vol": float(daily.std() * np.sqrt(year)) if len(daily) > 20 else NAN,
        "max_dd": float((window / window.cummax() - 1).min()),
    }


# ---------- checks ----------

def _check_trend_200(ind: pd.DataFrame, _bench) -> Signal | None:
    last = ind.iloc[-1]
    if not _ok(last.sma200):
        return None
    gap = last.Close / last.sma200 - 1
    pts = grade(gap, [(0.05, 1), (0, 0.5), (-0.05, -0.5)], below=-1)
    note = ("Long-term uptrend: price holds above its 200-day average." if gap > 0
            else "Long-term downtrend: price is below its 200-day average.")
    return Signal("200-DMA trend", f"{gap:+.1%} vs 200-DMA", pts, 2.0, note)


def _check_ma_alignment(ind, _bench) -> Signal | None:
    last = ind.iloc[-1]
    if not _ok(last.ema20, last.sma50, last.sma200):
        return None
    stacked = [last.Close > last.ema20, last.ema20 > last.sma50, last.sma50 > last.sma200]
    count = sum(stacked)
    notes = {3: "Perfect bullish stack: Price > 20-EMA > 50-DMA > 200-DMA.",
             0: "Fully bearish stack: Price < 20-EMA < 50-DMA < 200-DMA."}
    return Signal("Moving-average stack", f"{count}/3 bullish", (count - 1.5) / 1.5, 1.5,
                  notes.get(count, "Mixed moving averages: trend is transitioning."))


def _check_cross(ind, _bench) -> Signal | None:
    diff = ind["sma50"] - ind["sma200"]
    if not _ok(diff.iloc[-1]):
        return None
    golden = diff.iloc[-1] > 0
    recent = _bars_since_cross(diff, 20)
    label = "Golden cross" if golden else "Death cross"
    when = f" ({recent} bars ago - fresh!)" if recent is not None else ""
    pts = (1.0 if recent is not None else 0.6) * (1 if golden else -1)
    return Signal("50/200 cross", label + when, pts, 1.0,
                  "50-DMA above 200-DMA." if golden else "50-DMA below 200-DMA.")


def _check_adx(ind, _bench) -> Signal | None:
    last = ind.iloc[-1]
    if not _ok(last.adx, last.plus_di, last.minus_di):
        return None
    bullish = last.plus_di > last.minus_di
    reading = f"ADX {last.adx:.0f}, +DI {last.plus_di:.0f} / -DI {last.minus_di:.0f}"
    if last.adx < 20:
        return Signal("ADX trend strength", reading, 0.0, 1.0, "No real trend (ADX < 20): range-bound.")
    strength = 1.0 if last.adx >= 25 else 0.5
    return Signal("ADX trend strength", reading, strength * (1 if bullish else -1), 1.0,
                  f"{'Strong' if strength == 1 else 'Developing'} {'up' if bullish else 'down'}trend.")


def _check_supertrend(ind, _bench) -> Signal:
    up = ind["st_dir"].iloc[-1] > 0
    flip = _bars_since_cross(ind["st_dir"], 10)
    when = f", flipped {flip} bars ago" if flip is not None else ""
    return Signal("Supertrend (10,3)", f"{'BUY' if up else 'SELL'} @ {price_text(ind['st_line'].iloc[-1])}{when}",
                  1.0 if up else -1.0, 1.5,
                  "Price above the Supertrend line: trend-followers are long." if up
                  else "Price below the Supertrend line: trend-followers are out.")


def _check_rsi(ind, _bench) -> Signal | None:
    value = ind["rsi"].iloc[-1]
    if not _ok(value):
        return None
    if value > 75:
        pts, note = -0.5, "Overbought: rally is stretched, pullback risk is high."
    elif value >= 55:
        pts, note = 1.0, "Bullish momentum zone (55-75)."
    elif value >= 45:
        pts, note = 0.0, "Neutral momentum."
    elif value >= 30:
        pts, note = -0.7, "Bearish momentum zone (30-45)."
    else:
        pts, note = 0.2, "Oversold: bounce possible, but trend is weak."
    return Signal("RSI (14)", f"{value:.1f}", pts, 1.5, note)


def _check_macd(ind, _bench) -> Signal | None:
    hist = ind["macd_hist"]
    if not _ok(hist.iloc[-1], hist.iloc[-2]):
        return None
    above, rising = hist.iloc[-1] > 0, hist.iloc[-1] > hist.iloc[-2]
    cross = _bars_since_cross(hist, 5)
    pts = {(True, True): 1.0, (True, False): 0.4, (False, True): -0.3, (False, False): -1.0}[(above, rising)]
    note = f"{'Bullish' if above else 'Bearish'} MACD, histogram {'rising' if rising else 'falling'}."
    if cross is not None:
        note += f" Fresh {'bullish' if above else 'bearish'} crossover {cross} bars ago."
    return Signal("MACD (12,26,9)", f"hist {price_text(hist.iloc[-1], 2, signed=True, grouped=False)}", pts, 1.5, note)


def _check_stochastic(ind, _bench) -> Signal | None:
    k, d, k_prev = ind["stoch_k"].iloc[-1], ind["stoch_d"].iloc[-1], ind["stoch_k"].iloc[-3]
    if not _ok(k, d, k_prev):
        return None
    if k > d and k_prev < 20:
        pts, note = 1.0, "Bullish turn up from oversold."
    elif k > 80:
        pts, note = -0.5, "Overbought territory."
    else:
        pts, note = (0.3, "%K above %D.") if k > d else (-0.3, "%K below %D.")
    return Signal("Stochastic (14,3)", f"%K {k:.0f} / %D {d:.0f}", pts, 0.5, note)


def _check_bollinger(ind, _bench) -> Signal | None:
    pct_b = ind["pct_b"].iloc[-1]
    if not _ok(pct_b):
        return None
    if pct_b > 1:
        pts, note = -0.3, "Closed above the upper band: stretched."
    elif pct_b >= 0.5:
        pts, note = 0.5, "Riding the upper half of the bands."
    elif pct_b >= 0:
        pts, note = -0.3, "Lower half of the bands: sellers in control."
    else:
        pts, note = 0.2, "Below the lower band: oversold extreme."
    return Signal("Bollinger %B", f"{pct_b:.2f}", pts, 0.75, note)


def _check_obv(ind, _bench) -> Signal | None:
    if len(ind) < 25:
        return None
    obv_delta = ind["obv"].iloc[-1] - ind["obv"].iloc[-SPANS.month]
    price_delta = ind["Close"].iloc[-1] / ind["Close"].iloc[-SPANS.month] - 1
    obv_up, price_up = obv_delta > 0, price_delta > 0
    pts, note = {
        (True, True): (1.0, "Accumulation: volume confirms the rise."),
        (True, False): (0.5, "Quiet accumulation on dips (bullish divergence)."),
        (False, True): (-0.5, "Rally on weak volume: not confirmed."),
        (False, False): (-1.0, "Distribution: volume confirms the decline."),
    }[(obv_up, price_up)]
    return Signal("On-balance volume (20d)", f"OBV {'up' if obv_up else 'down'}, price {price_delta:+.1%}", pts, 1.5, note)


def _check_volume_surge(ind, _bench) -> Signal | None:
    avg50 = ind["vol_avg50"].iloc[-1]
    if not _ok(avg50) or avg50 == 0:
        return None
    ratio = ind["Volume"].tail(5).mean() / avg50
    if ratio < 1.5:
        return None
    up = ind["Close"].iloc[-1] > ind["Close"].iloc[-6]
    return Signal("Volume surge", f"{ratio:.1f}x 50-day avg", 0.6 if up else -0.6, 0.75,
                  "Heavy buying volume." if up else "Heavy selling volume.")


def _check_relative_strength(ind, bench: pd.Series | None) -> Signal | None:
    if bench is None or len(bench) < SPANS.half + 4 or len(ind) < SPANS.half + 4:
        return None
    rs3 = _ret(ind["Close"], SPANS.quarter) - _ret(bench, SPANS.quarter)
    rs6 = _ret(ind["Close"], SPANS.half) - _ret(bench, SPANS.half)
    pts = 1.0 if rs3 > 0 and rs6 > 0 else -1.0 if rs3 < 0 and rs6 < 0 else 0.0
    note = {1.0: f"Outperforming {INDEX} over 3 and 6 months: market leader.",
            -1.0: f"Lagging {INDEX} over 3 and 6 months: market laggard."}.get(pts, f"Mixed vs {INDEX}.")
    return Signal(RS_SIGNAL, f"3M {rs3:+.1%}, 6M {rs6:+.1%}", pts, 2.0, note)


def extension_atr(ind: pd.DataFrame) -> float:
    """How many ATRs price sits above (+) or below (-) its 20-EMA."""
    last = ind.iloc[-1]
    return float((last.Close - last.ema20) / last.atr) if _ok(last.ema20, last.atr) and last.atr else NAN


def _check_extension(ind, _bench) -> Signal | None:
    gap = extension_atr(ind)
    if not _ok(gap) or abs(gap) <= 2:
        return None
    ema20 = ind["ema20"].iloc[-1]
    if gap > EXTENDED_ATR:
        return Signal("Extension vs 20-EMA", f"{gap:.1f} ATR above", -0.8, 1.0,
                      f"Over-extended after a sharp run: chasing risk. Better entry on a pullback toward {price_text(ema20)}.")
    if gap > 2:
        return Signal("Extension vs 20-EMA", f"{gap:.1f} ATR above", -0.3, 1.0, "Stretched above the 20-EMA.")
    return Signal("Extension vs 20-EMA", f"{gap:.1f} ATR below", 0.2, 1.0,
                  "Far below the 20-EMA: snap-back bounce possible.")


CHECKS = (_check_trend_200, _check_ma_alignment, _check_cross, _check_adx, _check_supertrend,
          _check_rsi, _check_macd, _check_stochastic, _check_bollinger, _check_obv,
          _check_volume_surge, _check_relative_strength, _check_extension)


def analyze_technical(ind: pd.DataFrame, benchmark: pd.Series | None) -> list[Signal]:
    return [s for check in CHECKS if (s := check(ind, benchmark)) is not None]
