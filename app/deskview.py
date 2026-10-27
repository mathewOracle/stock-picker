"""View-model for the order desk: what each tab lists, in what order, and what the detail panel shows.

No FastAPI and no HTML in here, so the ranking and filtering rules are unit-testable and main.py stays thin.

Buy intensity is the app's own 0-100 score for the tab: the composite score (swing) or the intraday bias (intraday).
Short intensity only exists intraday, where a short is a real trade: it is 100 - bias.
"""

import time
from collections import Counter
from datetime import datetime

from app import analysis, data
from app.broker import desk
from app.intraday import analysis as intraday
from app.intraday.indicators import SQUARE_OFF
from app.market import MARKET
from app.research import signal_record
from app.research.backtest import MAX_HOLD as SWING_MAX_HOLD
from app.scoring import BUY_LEVELS
from app.universe import STOCKS

TABS = ("swing", "intraday")
RANKS = ("long", "short")
DESK_CAPITAL, DESK_RISK = 100_000, desk.MAX_RISK_PCT   # the sizer defaults; the browser can lower them per request
SWING_PILLARS, INTRADAY_PILLARS = ("Fundamental", "Technical", "Chart"), ("Technical", "Context")
KIND = {"swing": "ohlcv", "intraday": "intraday"}   # cache key prefix per tab
SWING_STALE_AFTER = 4 * 86_400       # seconds: a weekend plus one market holiday is normal, more is not
INTRADAY_STALE_AFTER = 15 * 60       # seconds, and only while the market is open (after the close the last bars ARE the latest)
INTRADAY_SIGNAL_NOTE = ("Intraday signals are not scored one by one: the playbook setups are backtested as a whole "
                        "(see Research & validation).")


class UnknownSymbol(LookupError):
    pass


class NoAnalysis(LookupError):
    """The symbol is valid but this side has no analysis for it yet (no data fetched)."""


# ---------- data age: the "don't trade on old prices" rule, in one place ----------

def _span(seconds: float) -> str:
    minutes, hours, days = seconds / 60, seconds / 3600, seconds / 86_400
    return f"{minutes:.0f} min" if hours < 1 else f"{hours:.0f} h" if days < 2 else f"{days:.0f} days"


def freshness(fetched: float | None, tab: str, market_open: bool, now: float) -> dict:
    """How old a stock's data is, whether that is too old to place an order on, and why."""
    if fetched is None:
        return {"label": "never fetched", "stale": True, "why": "No data has been fetched for this stock yet: refresh first."}
    age = max(0.0, now - fetched)
    limit = SWING_STALE_AFTER if tab == "swing" else INTRADAY_STALE_AFTER if market_open else None
    stale = limit is not None and age > limit
    what = "Daily prices" if tab == "swing" else "The 5-minute bars"
    return {"label": "just now" if age < 60 else f"{_span(age)} ago", "stale": stale,
            "why": f"{what} are {_span(age)} old: re-analyse or refresh before ordering." if stale else ""}


def _market_open(tab: str) -> bool:
    return tab == "intraday" and bool(getattr(intraday.build().status, "is_open", False))


def symbol_freshness(symbol: str, tab: str) -> dict:
    return freshness(data.symbol_fetched_at(symbol, KIND[tab]), tab, _market_open(tab), time.time())


# ---------- reports and drafts ----------

def build_tab(tab: str):
    return analysis.build() if tab == "swing" else intraday.build()


def report_for(symbol: str, tab: str):
    report = build_tab(tab).get(symbol)
    if report is None:
        raise NoAnalysis(f"No {tab} analysis for {symbol}: refresh the data first")
    return report


def now() -> datetime:
    """The exchange's clock: "one order per day" and the US rule windows are the exchange's days, not this laptop's."""
    return datetime.now(MARKET.clock.tz)


def draft(symbol: str, mode: str, capital: float, risk: float, qty: int | None, report=None, account: str = "") -> desk.Draft:
    report = report or report_for(symbol, mode)
    ref = desk.swing_reference(symbol) if mode == "swing" else desk.intraday_reference(report)
    return desk.build_draft(mode, symbol, report, ref, capital, risk, qty, account=account, now=now())


def order_card(symbol: str, mode: str, report) -> dict:
    if mode == "swing":
        extra = {"title": f"Swing order (long only, up to {SWING_MAX_HOLD} sessions)", "plan": report.plan, "why": report.blockers}
    else:
        extra = {"title": f"Intraday order (same day, flat by {SQUARE_OFF:%H:%M})",
                 "plan": report.best.plan if report.best else None, "why": [report.reason]}
    fresh = symbol_freshness(symbol, mode)
    return {"mode": mode, "verdict": report.verdict, "draft": draft(symbol, mode, DESK_CAPITAL, DESK_RISK, None, report),
            "recorded": desk.recorded_today(mode, symbol, now()), "blocked": fresh["why"], **extra}


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


def intraday_quality(report) -> float:
    """Explainable opportunity rank; this is quality ordering, not a fabricated probability of profit."""
    kind_points = {"setup": 400.0, "candidate": 300.0, "wait": 100.0, "none": 0.0}
    kind = intraday_kind(report.verdict)
    score = kind_points[kind]
    setup = getattr(report, "best", None)
    if setup is None:
        return score
    evidence = getattr(report, "evidence", {}).get(f"{setup.playbook.key}:{setup.side}", {})
    if evidence.get("status") == "supported":
        score += 50.0
    # Reward/risk is capped so one extreme estimate cannot overwhelm a validated setup.
    score += min(float(getattr(setup.plan, "reward_risk", 0.0)), 4.0) * 10.0
    score += min(abs(report.scores.get("bias", 50.0) - 50.0), 50.0) * 0.1
    return score


def intraday_rows(scan, rank: str = "quality") -> list[dict]:
    """Every stock, quality-first by default; explicit long/short ranks remain available for tape views."""
    rows = [{"r": r, "buy": r.scores["bias"], "short": 100 - r.scores["bias"], "kind": intraday_kind(r.verdict),
             "lean": lean(r.scores["bias"]), "quality": intraday_quality(r)} for r in scan.reports]
    # Quality is the primary key in both modes; the selected intensity breaks ties.
    key = "qualitybuy" if rank == "long" else "qualityshort"
    for row in rows:
        row[key] = row["quality"] * 1000.0 + row["buy" if rank == "long" else "short"]
    return sorted(rows, key=lambda row: -row[key])


# ---------- overview: Careers-Monitor-style status tiles and the "needs attention" strip ----------

ATTENTION_LIMIT = 12
# blocking problems first, then what you can act on, then near-misses (rows keep their intensity order within each)
ATTENTION_ORDER = {"crit": 0, "ok": 1, "warn": 2}


def tally(rows: list[dict], tab: str) -> dict[str, int]:
    """Counts for the tiles: verdict groups (swing) or setup kinds and tape lean (intraday)."""
    if tab == "swing":
        verdicts = Counter(row["r"].verdict for row in rows)
        return {"buy": sum(verdicts[v] for v in BUY_LEVELS), "watch": verdicts["Watchlist"], "hold": verdicts["Hold"],
                "avoid": verdicts["Avoid"], "candidate": sum(row["candidate"] for row in rows), "total": len(rows)}
    kinds, leans = Counter(row["kind"] for row in rows), Counter(row["lean"] for row in rows)
    near_miss = sum(row["kind"] == "none" and bool(row["r"].setups) for row in rows)   # a pattern found, a check failed
    return {"setup": kinds["setup"], "candidate": kinds["candidate"], "near_miss": near_miss,
            "quiet": kinds["wait"] + kinds["none"] - near_miss,
            "long": leans["long"], "short": leans["short"], "flat": leans["flat"], "total": len(rows)}


def attention(tab: str, rows: list[dict], fresh: dict) -> tuple[list[dict], int]:
    """(the first ATTENTION_LIMIT items, how many there are). An item with a symbol selects that stock when clicked."""
    items = [{"status": "crit", "label": "Stale data", "reason": f"oldest data {fresh['label']}: refresh before ordering",
              "symbol": ""}] if fresh["stale"] else []
    for row in rows:
        r = row["r"]
        if tab == "swing" and r.verdict in BUY_LEVELS:
            items.append({"status": "ok", "label": r.name, "reason": f"{r.verdict}, validated", "symbol": r.symbol})
        elif tab == "swing" and row["candidate"]:
            items.append({"status": "warn", "label": r.name, "reason": "rules say Buy, not validated", "symbol": r.symbol})
        elif tab == "intraday" and row["kind"] in ("setup", "candidate"):
            items.append({"status": "ok" if row["kind"] == "setup" else "warn", "label": r.name,
                          "reason": r.verdict if row["kind"] == "setup" else r.reason, "symbol": r.symbol})
    items.sort(key=lambda item: ATTENTION_ORDER[item["status"]])
    return items[:ATTENTION_LIMIT], len(items)


def pick(rows: list[dict], symbol: str):
    """The selected report: `symbol` if this tab has it, else the top-ranked one (None for an empty tab)."""
    for row in rows:
        if row["r"].symbol == symbol:
            return row["r"]
    return rows[0]["r"] if rows else None


# ---------- page contexts ----------

def detail_context(tab: str, report) -> dict:
    ctx = {"tab": tab, "r": report, "signals": signal_rows(report, tab), "card": order_card(report.symbol, tab, report),
           "fetched": data.symbol_fetched_at(report.symbol, KIND[tab]), "fresh": symbol_freshness(report.symbol, tab)}
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
           "oldest": data.oldest_stock_refresh(KIND[tab]),
           "orders": desk.recent_orders()}
    ctx["oldest_fresh"] = freshness(ctx["oldest"], tab, _market_open(tab), time.time())
    ctx["tally"] = tally(rows, tab)
    ctx["attention"], ctx["attention_total"] = attention(tab, rows, ctx["oldest_fresh"])
    ctx["a" if tab == "swing" else "scan"] = result
    if selected is not None:
        ctx.update(detail_context(tab, selected))
    return ctx


def row_for(tab: str, symbol: str) -> dict:
    """The list row for one stock (used to refresh it in place after a re-analysis)."""
    result = build_tab(tab)
    rows = swing_rows(result) if tab == "swing" else intraday_rows(result)
    return next(row for row in rows if row["r"].symbol == symbol)
