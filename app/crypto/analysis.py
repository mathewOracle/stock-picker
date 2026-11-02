"""Crypto glue: cached data -> technical + chart + tokenomics report per coin, plus the crypto market's context.

The technical and chart pillars, the trade plan and the verdict gates are the SAME code the stock pages use
(app/pricecheck.py, app/scoring.py); only the fundamental pillar (app/crypto/tokenomics.py), the hard flags and the
pillar weights are crypto's own. Relative strength is measured against Bitcoin.
"""

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app import data
from app.crypto import coindata
from app.crypto.tokenomics import HARD_FLAGS, PILLAR_WEIGHTS, analyze_tokenomics, coin_metrics, tokenomic_flags
from app.indicators import compute_indicators
from app.market import MARKET
from app.patterns import ChartReport
from app.pricecheck import assess_price
from app.scoring import Gate, composite, decide
from app.signals import Signal, score, thesis
from app.technical import beta, price_metrics, traded_value
from app.tradeplan import TradePlan
from app.universe import BENCHMARK, INDICES, STOCKS

MIN_BARS = 130
VOL_WINDOW = 30                 # Bitcoin's realised volatility: the crypto market's fear gauge (there is no VIX)
NERVOUS_VOL = 0.70              # annualised; Bitcoin usually runs 40-60%
ALT_SEASON, BTC_SEASON = 0.75, 0.25   # share of altcoins beating Bitcoin over 90 days (the usual "altseason" yardstick)
WEEKDAY_YEAR = 252
MIN_DISTINCT_CLOSES = 0.5      # under half the last year's closes distinct = the feed is rounding the price away


@dataclass
class CoinReport:
    symbol: str
    name: str
    category: str
    metrics: dict
    technical: list[Signal]
    chart: ChartReport
    fundamental: list[Signal]
    plan: TradePlan
    scores: dict[str, float] = field(default_factory=dict)
    verdict: str = ""
    gates: list[Gate] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def ticker(self) -> str:
        return MARKET.short_symbol(self.symbol)

    @property
    def pillars(self) -> list[tuple[str, float, list[Signal]]]:
        return [("Tokenomics", self.scores["fundamental"], self.fundamental),
                ("Technical", self.scores["technical"], self.technical),
                ("Chart", self.scores["chart"], self.chart.signals)]

    @property
    def blockers(self) -> list[str]:
        return [g.name for g in self.gates if not g.passed]

    @property
    def thesis(self) -> list[str]:
        return thesis(self.pillars)


@dataclass
class Overview:
    reports: list[CoinReport] = field(default_factory=list)
    indices: list[dict] = field(default_factory=list)       # macro context: S&P 500, Nasdaq, dollar, gold
    categories: list[dict] = field(default_factory=list)
    regime: dict = field(default_factory=dict)
    btc_vol: float | None = None
    alt_season: dict = field(default_factory=dict)
    dominance: float | None = None                            # Bitcoin's share of the TRACKED coins' market cap
    breadth_200dma: float | None = None
    total_cap: float | None = None
    as_of: str | None = None
    refreshed_at: float | None = None

    def get(self, symbol: str) -> CoinReport | None:
        return next((r for r in self.reports if r.symbol == symbol), None)


def bars_per_year(index: pd.DatetimeIndex) -> int:
    """365 for a 24/7 series, 252 for a weekday one (indices shown next to coins)."""
    return MARKET.trading_days if (index.dayofweek >= 5).any() else WEEKDAY_YEAR


def realised_vol(close: pd.Series, days: int = VOL_WINDOW) -> float | None:
    daily = close.pct_change().dropna().tail(days)
    return float(daily.std() * np.sqrt(MARKET.trading_days)) if len(daily) >= days // 2 else None


def coarse_prices(close: pd.Series) -> bool:
    """True when the feed quantises the price into a staircase (Yahoo rounds daily bars to 6 decimals, so SHIB at
    $0.0000046 has 1-2 significant figures). ATR, levels and targets computed on a staircase are meaningless."""
    recent = close.tail(MARKET.spans.year)
    return recent.nunique() < MIN_DISTINCT_CLOSES * len(recent)


def crypto_regime(btc: dict | None, vol: float | None) -> dict:
    """Bitcoin leads the asset class: its trend + its realised volatility are the tape."""
    if not btc or not math.isfinite(btc.get("pct_vs_200dma", float("nan"))):
        return {"label": "Unknown", "detail": "No Bitcoin data yet.", "tone": "slate"}
    below_200, drawdown = btc["pct_vs_200dma"] < 0, btc["off_high"]
    if below_200 and drawdown < -0.20:
        return {"label": "Crypto winter / Bearish", "tone": "red",
                "detail": f"Bitcoin is {drawdown:.0%} off its 52-week high and below its 200-day average. "
                          "Altcoins usually fall harder: size small or stand aside."}
    if below_200:
        return {"label": "Weak / Range-bound", "tone": "amber",
                "detail": "Bitcoin is under its 200-day average. Favour the strongest coins and keep stops tight."}
    if vol is not None and vol > NERVOUS_VOL:
        return {"label": "Uptrend, but violent", "tone": "amber",
                "detail": f"Trend is up but Bitcoin's 30-day volatility is {vol:.0%} a year. Expect sharp shakeouts."}
    return {"label": "Healthy uptrend", "tone": "green", "detail": "Bitcoin is above its 200-day average with calm volatility."}


def alt_season(reports: list[CoinReport]) -> dict:
    """Share of altcoins beating Bitcoin over the last quarter: >= 75% altcoin season, <= 25% Bitcoin season."""
    btc = next((r for r in reports if r.symbol == BENCHMARK), None)
    alts = [r for r in reports if r.symbol != BENCHMARK and math.isfinite(r.metrics["ret_3m"])]
    if btc is None or not alts or not math.isfinite(btc.metrics["ret_3m"]):
        return {}
    share = sum(r.metrics["ret_3m"] > btc.metrics["ret_3m"] for r in alts) / len(alts)
    label = "Altcoin season" if share >= ALT_SEASON else "Bitcoin season" if share <= BTC_SEASON else "Mixed"
    return {"share": share, "label": label, "alts": len(alts)}


def _report(coin: data.StockData, ind: pd.DataFrame, bench: pd.Series | None, supply: dict) -> CoinReport:
    pa = assess_price(ind, bench)   # identical to the stock pages: technical + chart + plan
    category = MARKET.category(coin.symbol)
    tok = coin_metrics(coin.fundamentals.get("info", {}), pa.metrics["price"], supply)
    metrics = {**pa.metrics, **tok, "sector": category, "beta": beta(ind["Close"], bench),
               "traded_value": traded_value(ind), "vol_30d": realised_vol(ind["Close"])}
    report = CoinReport(coin.symbol, STOCKS[coin.symbol], category, metrics, pa.technical, pa.chart,
                        analyze_tokenomics(tok, category), pa.plan)
    report.scores = {"fundamental": score(report.fundamental), "technical": pa.scores["technical"],
                     "chart": pa.scores["chart"]}
    report.scores["composite"] = composite(report.scores, PILLAR_WEIGHTS)
    report.flags = pa.flags + tokenomic_flags(tok, category) + (["Coarse price data"] if coarse_prices(ind["Close"]) else [])
    report.verdict, report.gates = decide(
        {**report.scores, "reward_risk": pa.plan.reward_risk, "extension": metrics["extension"]}, report.flags, HARD_FLAGS)
    return report


def _indices() -> list[dict]:
    out = []
    for symbol, name in INDICES.items():
        frame = data.load_ohlcv(symbol)
        if frame is not None and len(frame) > 30:
            out.append({"symbol": symbol, "name": name, **price_metrics(frame["Close"], year=bars_per_year(frame.index))})
    return out


def _categories(reports: list[CoinReport]) -> list[dict]:
    frame = pd.DataFrame([{"category": r.category, "score": r.scores["composite"], "ret_3m": r.metrics["ret_3m"],
                           "ret_12m": r.metrics["ret_12m"]} for r in reports])
    return (frame.groupby("category")
            .agg(coins=("score", "size"), avg_score=("score", "mean"),
                 avg_ret_3m=("ret_3m", "mean"), avg_ret_12m=("ret_12m", "mean"))
            .sort_values("avg_score", ascending=False).reset_index().to_dict("records"))


def _build() -> Overview:
    result = Overview(refreshed_at=data.last_refresh(), indices=_indices())
    coins = [c for c in data.load_stocks() if len(c.ohlcv) > MIN_BARS]
    if not coins:
        return result
    bench_frame = data.load_ohlcv(BENCHMARK)
    bench = bench_frame["Close"] if bench_frame is not None else None
    supply = coindata.supply_history()
    result.reports = sorted(
        (_report(c, compute_indicators(c.ohlcv), None if c.symbol == BENCHMARK else bench, supply.get(c.symbol, {}))
         for c in coins),
        key=lambda r: r.scores["composite"], reverse=True)
    btc = result.get(BENCHMARK)
    result.btc_vol = btc.metrics["vol_30d"] if btc else None
    result.regime = crypto_regime(btc.metrics if btc else None, result.btc_vol)
    result.alt_season = alt_season(result.reports)
    caps = {r.symbol: r.metrics["market_cap"] for r in result.reports if math.isfinite(r.metrics["market_cap"])}
    result.total_cap = sum(caps.values()) or None
    result.dominance = caps[BENCHMARK] / result.total_cap if result.total_cap and BENCHMARK in caps else None
    result.breadth_200dma = float(np.mean([r.metrics["pct_vs_200dma"] > 0 for r in result.reports]))
    result.categories = _categories(result.reports)
    result.as_of = max(c.ohlcv.index[-1] for c in coins).strftime("%d %b %Y")
    return result


_memo: tuple[tuple, Overview] | None = None


def build() -> Overview:
    """Recomputed only when the cached prices or the supply history change."""
    global _memo
    stamp = (data.last_refresh(), data.last_research())
    if _memo is None or _memo[0] != stamp:
        _memo = (stamp, _build())
    return _memo[1]
