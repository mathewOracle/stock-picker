"""View-model for the order desk: what each tab lists, in what order, and what the detail panel shows.

No FastAPI and no HTML in here, so the ranking and filtering rules are unit-testable and main.py stays thin.

Buy intensity is the app's own 0-100 score for the tab: the composite score (swing) or the intraday bias (intraday).
Short intensity only exists intraday, where a short is a real trade: it is 100 - bias.
"""

from datetime import datetime

from app import analysis, data
from app.broker import desk
from app.intraday import analysis as intraday
from app.intraday.indicators import SQUARE_OFF
from app.research import signal_record
from app.research.backtest import MAX_HOLD as SWING_MAX_HOLD
from app.scoring import BUY_LEVELS
from app.universe import STOCKS

TABS = ("swing", "intraday")
RANKS = ("long", "short")
DESK_CAPITAL, DESK_RISK = 100_000, 1.0   # the sizer's defaults; the browser can change them per request
SWING_PILLARS, INTRADAY_PILLARS = ("Fundamental", "Technical", "Chart"), ("Technical", "Context")
INTRADAY_SIGNAL_NOTE = ("Intraday signals are not scored one by one: the playbook setups are backtested as a whole "
                        "(see Research & validation).")


class UnknownSymbol(LookupError):
    pass


class NoAnalysis(LookupError):
    """The symbol is valid but this side has no analysis for it yet (no data fetched)."""


# ---------- reports and drafts ----------

def build_tab(tab: str):
    return analysis.build() if tab == "swing" else intraday.build()


def report_for(symbol: str, tab: str):
    report = build_tab(tab).get(symbol)
    if report is None:
        raise NoAnalysis(f"No {tab} analysis for {symbol}: refresh the data first")
    return report


def draft(symbol: str, mode: str, capital: float, risk: float, qty: int | None, report=None) -> desk.Draft:
    report = report or report_for(symbol, mode)
    ref = desk.swing_reference(symbol) if mode == "swing" else desk.intraday_reference(report)
    return desk.build_draft(mode, symbol, report, ref, capital, risk, qty)


def order_card(symbol: str, mode: str, report) -> dict:
    if mode == "swing":
        extra = {"title": f"Swing order (delivery, up to {SWING_MAX_HOLD} sessions)", "plan": report.plan, "why": report.blockers}
    else:
        extra = {"title": f"Intraday order (same day, flat by {SQUARE_OFF:%H:%M})",
                 "plan": report.best.plan if report.best else None, "why": [report.reason]}
    return {"mode": mode, "verdict": report.verdict, "draft": draft(symbol, mode, DESK_CAPITAL, DESK_RISK, None, report),
            "recorded": desk.recorded_today(mode, symbol, datetime.now()), **extra}


# ---------- signals ----------

def signal_rows(report, tab: str) -> list[dict]:
    """One row per signal, tagged with its pillar and (swing only) its backtested track record."""
    if tab == "swing":
        records = signal_record.records()
        return [{"s": s, "pillar": label, "record": records.get(s.name), "evidence": signal_record.describe(records.get(s.name))}
                for label, _, signals in report.pillars for s in signals]
    return [{"s": s, "pillar": label, "record": None, "evidence": INTRADAY_SIGNAL_NOTE}
            for label, signals in (("Technical", report.technical), ("Context", report.context)) for s in signals]


def evidence_counts(rows: list[dict]) -> tuple[int, int]:
    """(signals with a proven edge, signals that had enough history to be judged)."""
    judged = [row["record"] for row in rows if row["record"] and row["record"]["status"] != "insufficient"]
    return sum(r["status"] == "edge" for r in judged), len(judged)


# ---------- lists ----------

def swing_rows(result) -> list[dict]:
    """Every stock, best buy intensity first. `candidate` = the rules said Buy but validation did not agree."""
    rows = [{"r": r, "intensity": r.scores["composite"], "candidate": r.rule_verdict in BUY_LEVELS and r.verdict not in BUY_LEVELS}
            for r in result.reports]
    return sorted(rows, key=lambda row: -row["intensity"])


def intraday_kind(verdict: str) -> str:
    return "setup" if verdict.endswith("setup") else "candidate" if verdict.endswith("candidate") else "wait" if verdict == "Wait" else "none"


def lean(bias: float) -> str:
    return "long" if bias >= intraday.LONG_BIAS else "short" if bias <= intraday.SHORT_BIAS else "flat"


def intraday_rows(scan, rank: str = "long") -> list[dict]:
    """Every stock ranked by buy intensity (rank='long') or short intensity (rank='short')."""
    rows = [{"r": r, "buy": r.scores["bias"], "short": 100 - r.scores["bias"], "kind": intraday_kind(r.verdict),
             "lean": lean(r.scores["bias"])} for r in scan.reports]
    return sorted(rows, key=lambda row: -row["buy" if rank == "long" else "short"])


def pick(rows: list[dict], symbol: str):
    """The selected report: `symbol` if this tab has it, else the top-ranked one (None for an empty tab)."""
    for row in rows:
        if row["r"].symbol == symbol:
            return row["r"]
    return rows[0]["r"] if rows else None


# ---------- page contexts ----------

def detail_context(tab: str, report) -> dict:
    ctx = {"tab": tab, "r": report, "signals": signal_rows(report, tab), "card": order_card(report.symbol, tab, report),
           "fetched": data.symbol_fetched_at(report.symbol, "ohlcv" if tab == "swing" else "intraday")}
    ctx["proven"], ctx["tested"] = evidence_counts(ctx["signals"])
    ctx["bar"] = signal_record.bar()
    ctx["pillars"] = SWING_PILLARS if tab == "swing" else INTRADAY_PILLARS
    return ctx


def page_context(tab: str, symbol: str, rank: str) -> dict:
    if symbol and symbol not in STOCKS:
        raise UnknownSymbol(symbol)
    result = build_tab(tab)
    rows = swing_rows(result) if tab == "swing" else intraday_rows(result, rank)
    selected = pick(rows, symbol)
    ctx = {"tab": tab, "rank": rank, "stocks": rows, "selected": selected, "capital": DESK_CAPITAL, "risk": DESK_RISK,
           "sectors": sorted({row["r"].metrics["sector"] for row in rows}) if tab == "swing" else [],
           "oldest": data.oldest_stock_refresh("ohlcv" if tab == "swing" else "intraday"),
           "orders": desk.recent_orders()}
    ctx["a" if tab == "swing" else "scan"] = result
    if selected is not None:
        ctx.update(detail_context(tab, selected))
    return ctx


def row_for(tab: str, symbol: str) -> dict:
    """The list row for one stock (used to refresh it in place after a re-analysis)."""
    result = build_tab(tab)
    rows = swing_rows(result) if tab == "swing" else intraday_rows(result)
    return next(row for row in rows if row["r"].symbol == symbol)
