"""Intraday orchestration: snapshot + context + setups -> one verdict per stock, plus market phase."""

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, time

import pandas as pd

from app import analysis as swing
from app import data
from app.intraday.checks import DailyContext, intraday_context, intraday_technical, tradeability_issues
from app.intraday.economics import describe as describe_math
from app.intraday.economics import trade_math
from app.intraday.indicators import LAST_ENTRY_BAR, NO_NEW_ENTRIES, OPENING_RANGE_END, bar_start
from app.intraday.setups import COUNTER_TREND, Setup, detect_setups
from app.intraday.snapshot import Snapshot, build_snapshot
from app.market import MARKET
from app.market.profile import shift
from app.rules import intraday_block
from app.signals import Signal, score
from app.universe import BENCHMARK, STOCKS

TZ = MARKET.clock.tz
MIN_RR = 1.5
BIAS_WEIGHTS = {"technical": 0.7, "context": 0.3}
LONG_BIAS, SHORT_BIAS = 55, 45
STALE_MINUTES = 10


@dataclass(frozen=True)
class MarketStatus:
    phase: str
    is_open: bool
    accepting_entries: bool
    session_date: date | None
    last_bar: datetime | None
    note: str
    index_change: float = float("nan")


@dataclass
class IntradayReport:
    symbol: str
    name: str
    sector: str
    snapshot: Snapshot
    context_data: DailyContext
    technical: list[Signal]
    context: list[Signal]
    setups: list[Setup]
    issues: list[str]
    scores: dict[str, float] = field(default_factory=dict)
    verdict: str = ""
    reason: str = ""
    best: Setup | None = None
    evidence: dict[str, dict] = field(default_factory=dict)     # "playbook:side" -> backtest record
    economics: dict[str, dict] = field(default_factory=dict)    # "playbook:side" -> cost in R, break-even win rate
    sentiment: dict | None = None                                # daily news sentiment (swing-horizon, informational)
    ml_prob: float | None = None                                 # swing ML model's P(trade wins), only if adopted


@dataclass
class IntradayScan:
    reports: list[IntradayReport] = field(default_factory=list)
    status: MarketStatus | None = None
    refreshed_at: float | None = None
    ml_note: str = ""                                            # why the ML column reads the way it does

    def get(self, symbol: str) -> IntradayReport | None:
        return next((r for r in self.reports if r.symbol == symbol), None)


def tz_label(now: datetime | None = None) -> str:
    """The exchange's zone abbreviation right now (IST; EST or EDT), so times on screen say whose clock they are."""
    return f"{(now or datetime.now(TZ)).astimezone(TZ):%Z}"


def entry_cutoff(day: date) -> time:
    """No new entries after this on `day`: 45 minutes before THAT day's close (a US half-day closes at 13:00)."""
    hours = MARKET.session(day)
    return NO_NEW_ENTRIES if hours is None else shift(hours.close, -MARKET.clock.last_entry_before_close)


def market_phase(now: datetime) -> tuple[str, bool, bool]:
    """(label, is_open, accepting_new_entries) for cash-market hours; holidays and half-days if the profile knows them."""
    if now.weekday() >= 5:
        return "Closed (weekend)", False, False
    hours = MARKET.session(now.date())
    if hours is None:
        return "Closed (holiday)", False, False
    t = now.time()
    if t < MARKET.clock.early_start:
        return MARKET.clock.overnight_label, False, False
    if t < hours.open:
        return MARKET.clock.early_label, False, False
    if t < OPENING_RANGE_END:
        return "Opening range forming", True, False
    if t < entry_cutoff(now.date()):
        return "Open: trading window", True, True
    if t < hours.close:
        return "Open: no new entries (square-off time)", True, False
    return "Closed", False, False


def _half_day_note(day: date) -> str:
    hours = MARKET.session(day)
    if hours is None or hours.close >= MARKET.clock.close:
        return ""
    square_off = shift(hours.close, -MARKET.clock.square_off_before_close)
    return f" Half-day: the market closes at {hours.close:%H:%M}, so be flat by {square_off:%H:%M}."


def _status(now: datetime, index: Snapshot | None, last_bar: datetime | None) -> MarketStatus:
    phase, is_open, accepting = market_phase(now)
    session_date = index.session_date if index else None
    if not is_open:
        note = (f"Market closed. Showing how the last session ({session_date:%d %b}) ended. "
                "Use the next-session levels to plan tomorrow." if session_date else "Market closed.")
    elif session_date != now.date():
        note = "Market hours, but no bars for today yet (holiday, or data not refreshed)."
    elif last_bar and (now.replace(tzinfo=None) - last_bar).total_seconds() > STALE_MINUTES * 60:
        note = f"Data is from {last_bar:%H:%M}. Refresh for the latest bars (Yahoo can lag a few minutes)."
    else:
        note = f"Live session. Last bar {last_bar:%H:%M} {tz_label(now)}." if last_bar else "Live session."
    note += _half_day_note(now.date())
    return MarketStatus(phase, is_open and session_date == now.date(), accepting and session_date == now.date(),
                        session_date, last_bar, note, index.change if index else float("nan"))


def _earnings_in_days(ts: float, session_date: date) -> int | None:
    if not math.isfinite(ts):
        return None
    days = (datetime.fromtimestamp(ts, TZ).date() - session_date).days
    return days if days >= 0 else None


def _context(metrics: dict, scores: dict, session_date: date, sector_change: float, index_change: float) -> DailyContext:
    return DailyContext(
        traded_value=metrics["traded_value"], atr_pct=metrics["atr"] / metrics["price"],
        beta=metrics["beta"], daily_technical=scores["technical"], fundamental=scores["fundamental"],
        earnings_in_days=_earnings_in_days(metrics["earnings_ts"], session_date),
        sector_change=sector_change, index_change=index_change,
    )


def setup_evidence(evidence: dict | None, setup: Setup) -> dict:
    """The backtest record of this playbook+side. A missing record is 'not backtested', never a pass."""
    return ((evidence or {}).get("setups", {}).get(f"{setup.playbook.key}:{setup.side}")
            or {"status": "not backtested", "n": 0})


def describe_evidence(block: dict) -> str:
    if block["status"] == "not backtested":
        return "not backtested yet"
    if not block.get("n"):
        return "never fired in the backtest"
    return (f"backtest {block['status']} ({block['n']} trades, avg {block['avg_return']:+.2%} after costs, "
            f"t {block['t_stat']:.1f})")


def _too_late(report: IntradayReport, status: MarketStatus) -> bool:
    """No new entry from a signal bar closing after the entry cutoff -- the backtest never opens one that late.

    The wall clock catches lagging data during market hours; the bar time catches setups that fired on the
    last session's closing bars and would otherwise look tradeable all evening. The cutoff is that session's own
    (45 minutes before a half-day's early close too).
    """
    last = report.snapshot.day.index[-1]
    cutoff_bar = min(LAST_ENTRY_BAR, bar_start(entry_cutoff(last.date())))
    return (status.is_open and not status.accepting_entries) or last.time() > cutoff_bar


def decide(report: IntradayReport, status: MarketStatus, evidence: dict | None = None) -> tuple[str, str, Setup | None]:
    """Return (verdict, reason, best setup). Every 'No trade' says why.

    A setup that passes every live rule is only a *setup* if its playbook is also supported by the backtest;
    otherwise it is shown as a *candidate* (same idea as Buy -> Watchlist on the swing side). When several
    setups pass, a supported one always beats an unsupported one, whatever their reward/risk.
    """
    if report.issues:
        return "No trade", "; ".join(report.issues), None
    if status.is_open and status.phase == "Opening range forming":
        return "Wait", f"Opening range forms until {OPENING_RANGE_END:%H:%M}", None
    if not report.setups:
        return "No trade", "No playbook setup active", None
    bias = report.scores["bias"]
    aligned = [s for s in report.setups if s.playbook.key in COUNTER_TREND
               or (s.side == "Long" and bias >= LONG_BIAS) or (s.side == "Short" and bias <= SHORT_BIAS)]
    valid = [s for s in aligned if s.plan.reward_risk >= MIN_RR]
    if not valid:
        why = "fights the intraday bias" if not aligned else f"reward/risk below {MIN_RR}"
        return "No trade", f"{report.setups[0].playbook.name} found, but it {why}", None
    allowed = [s for s in valid if not intraday_block(report.snapshot.bars, s.side)]   # market rules, e.g. US Rule 201
    if not allowed:
        return "No trade", f"{valid[0].playbook.name} found, but {intraday_block(report.snapshot.bars, valid[0].side)}", None
    best = max(allowed, key=lambda s: (setup_evidence(evidence, s)["status"] == "supported", s.plan.reward_risk))
    if _too_late(report, status):
        return "No trade", f"Signal after {NO_NEW_ENTRIES:%H:%M}: no new entries (the backtest never opens a trade this late)", best
    block = setup_evidence(evidence, best)
    if block["status"] == "supported":
        return f"{best.side} setup", best.trigger, best
    return (f"{best.side} candidate",
            f"{best.trigger}. Not validated: {describe_evidence(block)}; {describe_math(trade_math(best.plan, block))}", best)


def _build(now: datetime) -> IntradayScan:
    scan = IntradayScan(refreshed_at=data.last_intraday_refresh())
    index_bars = data.load_intraday(BENCHMARK)
    index = build_snapshot(index_bars) if index_bars is not None else None
    swing_result = swing.build()
    snapshots = {}
    for symbol in STOCKS:
        bars, report = data.load_intraday(symbol), swing_result.get(symbol)
        if bars is not None and report is not None and (snap := build_snapshot(bars)) is not None:
            snapshots[symbol] = (snap, report)
    last_bar = max((s.day.index[-1] for s, _ in snapshots.values()), default=None)
    scan.status = _status(now, index, last_bar.to_pydatetime() if last_bar is not None else None)

    by_sector: dict[str, dict[str, float]] = {}
    for symbol, (snap, report) in snapshots.items():
        by_sector.setdefault(report.metrics["sector"], {})[symbol] = snap.change
    backtest = data.load_result("intraday_backtest")
    news = (data.load_result("news") or {}).get("stocks", {})
    scan.ml_note = swing_result.ml_note
    for symbol, (snap, sw) in snapshots.items():
        sector = sw.metrics["sector"]
        peers = [change for peer, change in by_sector[sector].items() if peer != symbol]
        ctx = _context(sw.metrics, sw.scores, snap.session_date,
                       statistics.mean(peers) if peers else float("nan"), scan.status.index_change)
        report = IntradayReport(symbol, STOCKS[symbol], sector, snap, ctx, intraday_technical(snap, ctx),
                                intraday_context(ctx), detect_setups(snap), tradeability_issues(ctx))
        report.scores = {"technical": score(report.technical), "context": score(report.context)}
        report.scores["bias"] = sum(report.scores[k] * w for k, w in BIAS_WEIGHTS.items())
        report.evidence = {f"{s.playbook.key}:{s.side}": setup_evidence(backtest, s) for s in report.setups}
        report.economics = {key: trade_math(s.plan, report.evidence[key])
                            for s in report.setups if (key := f"{s.playbook.key}:{s.side}")}
        report.sentiment = news.get(symbol)         # same daily headline score the swing page already computed
        report.ml_prob = sw.metrics.get("ml_prob")  # only set when the swing ML filter is adopted (it isn't, today)
        report.verdict, report.reason, report.best = decide(report, scan.status, backtest)
        scan.reports.append(report)

    rank = {"Long setup": 0, "Short setup": 0, "Long candidate": 0.5, "Short candidate": 0.5, "Wait": 1, "No trade": 2}
    scan.reports.sort(key=lambda r: (rank.get(r.verdict, 3), -abs(r.scores["bias"] - 50)))
    return scan


_memo: tuple[tuple, IntradayScan] | None = None


def build(now: datetime | None = None) -> IntradayScan:
    """Recomputed when either data set refreshes or the market phase changes."""
    global _memo
    now = now or datetime.now(TZ)
    backtest = data.load_result("intraday_backtest")
    key = (data.last_intraday_refresh(), data.last_refresh(), data.last_research(), market_phase(now)[0],
           now.strftime("%H:%M"), (backtest or {}).get("generated_at"))  # new evidence must not be a stale memo
    if _memo is None or _memo[0] != key:
        _memo = (key, _build(now))
    return _memo[1]


def _epoch(index: pd.DatetimeIndex) -> list[int]:
    """Exchange wall-clock -> epoch seconds as if UTC, so the chart's UTC axis reads in exchange time."""
    return [int(ts.timestamp()) for ts in index.tz_localize("UTC")]


def chart_payload(report: IntradayReport) -> dict:
    s = report.snapshot
    days = sorted(set(s.bars.index.date))[-2:]
    bars = s.bars[pd.Index(s.bars.index.date).isin(days)]
    times = _epoch(bars.index)

    def line(col: str) -> list[dict]:
        return [{"time": t, "value": round(float(v), 2)} for t, v in zip(times, bars[col]) if math.isfinite(v)]

    levels = [{"price": v, "title": k} for k, v in s.pivots.levels().items() if k in ("R2", "R1", "TC", "BC", "S1", "S2")]
    levels += [{"price": s.pdh, "title": "PDH"}, {"price": s.pdl, "title": "PDL"}]
    if s.opening_range:
        levels += [{"price": s.opening_range[0], "title": "OR high"}, {"price": s.opening_range[1], "title": "OR low"}]
    plan = report.best.plan if report.best else None
    return {
        "candles": [{"time": t, "open": r.Open, "high": r.High, "low": r.Low, "close": r.Close}
                    for t, r in zip(times, bars.itertuples())],
        "volume": [{"time": t, "value": float(r.Volume), "color": "#16a34a80" if r.Close >= r.Open else "#dc262680"}
                   for t, r in zip(times, bars.itertuples())],
        **{col: line(col) for col in ("vwap", "vwap_u2", "vwap_l2", "ema9", "ema21", "rsi")},
        "levels": levels,
        "plan": {"entry": plan.entry, "stop": plan.stop, "target1": plan.target1, "target2": plan.target2} if plan else None,
    }
