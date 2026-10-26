"""FastAPI app: swing dashboard, stock deep-dive, intraday scanner, and background refresh jobs."""

import math
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import analysis, data
from app.broker import desk
from app.intraday import analysis as intraday
from app.intraday import archive as intraday_archive
from app.intraday.checks import MIN_ATR_PCT, MIN_TRADED_VALUE_CR
from app.intraday.indicators import NO_NEW_ENTRIES, SQUARE_OFF
from app.intraday.setups import PLAYBOOKS
from app.jobs import RefreshJob
from app.research import pipeline, signal_record
from app.research.backtest import MAX_HOLD as SWING_MAX_HOLD
from app.research.ml import PROBA_GATE
from app.scoring import BUY_LEVELS, GATES, PILLAR_WEIGHTS, VERDICTS, WATCHLIST
from app.universe import STOCKS

BASE = Path(__file__).resolve().parent
app = FastAPI(title="India Stock Picker")
app.add_middleware(GZipMiddleware, minimum_size=1024)  # stock pages carry ~140 KB of chart JSON
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
jobs = {"daily": RefreshJob(data.refresh), "intraday": RefreshJob(intraday_archive.refresh),
        "research": RefreshJob(pipeline.run_all)}


def _is_nan(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def pct(value, signed: bool = True, digits: int = 1) -> str:
    return "–" if _is_nan(value) else f"{value * 100:{'+' if signed else ''}.{digits}f}%"


def num(value, digits: int = 1) -> str:
    return "–" if _is_nan(value) else f"{value:,.{digits}f}"


def pe(value) -> str:
    return "loss" if not _is_nan(value) and value >= 1000 else num(value)


def crore(value) -> str:
    return "–" if _is_nan(value) else f"₹{value / 1e7:,.0f} Cr"


def timestamp(value) -> str:
    return "never" if value is None else datetime.fromtimestamp(value).strftime("%d %b %Y, %H:%M")


templates.env.filters.update(pct=pct, num=num, pe=pe, crore=crore, timestamp=timestamp,
                              evidence_note=intraday.describe_evidence)
templates.env.globals.update(square_off=f"{SQUARE_OFF:%H:%M}", no_new_entries=f"{NO_NEW_ENTRIES:%H:%M}",
                             swing_max_hold=SWING_MAX_HOLD)  # the swing backtest's time exit, in sessions


# ---------- swing / positional ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    result = analysis.build()
    ctx = {
        "a": result, "nav": "swing",
        "buys": [r for r in result.reports if r.verdict in BUY_LEVELS],
        "candidates": [r for r in result.reports if r.rule_verdict in BUY_LEVELS and r.verdict not in BUY_LEVELS],
        "watchlist": [r for r in result.reports if r.verdict == "Watchlist"],
        "reports": result.reports,
        "sectors": sorted({r.metrics["sector"] for r in result.reports}),
        "verdicts": VERDICTS,
        "gates": GATES, "weights": PILLAR_WEIGHTS, "watch_rule": WATCHLIST,
    }
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/table", response_class=HTMLResponse)
def table(request: Request, sector: str = "", verdict: str = ""):
    reports = [r for r in analysis.build().reports
               if (not sector or r.metrics["sector"] == sector) and (not verdict or r.verdict == verdict)]
    return templates.TemplateResponse(request, "_table.html", {"reports": reports})


@app.get("/stock/{symbol}", response_class=HTMLResponse)
def stock(request: Request, symbol: str):
    report = analysis.build().get(symbol)
    if report is None:
        raise HTTPException(404, "Unknown symbol, or no data yet - hit Refresh on the dashboard")
    ctx = {"r": report, "chart": analysis.chart_payload(symbol, report), "weights": PILLAR_WEIGHTS,
           "nav": "swing", "has_intraday": intraday.build().get(symbol) is not None}
    return templates.TemplateResponse(request, "stock.html", ctx)


# ---------- intraday ----------

@app.get("/intraday", response_class=HTMLResponse)
def intraday_dashboard(request: Request):
    scan = intraday.build()
    ctx = {"scan": scan, "nav": "intraday", "playbooks": PLAYBOOKS.values(),
           "setups": [r for r in scan.reports if r.verdict.endswith("setup")],
           "min_rr": intraday.MIN_RR, "min_value": MIN_TRADED_VALUE_CR, "min_atr": MIN_ATR_PCT,
           "long_bias": intraday.LONG_BIAS, "short_bias": intraday.SHORT_BIAS}
    return templates.TemplateResponse(request, "intraday.html", ctx)


@app.get("/intraday/{symbol}", response_class=HTMLResponse)
def intraday_stock(request: Request, symbol: str):
    scan = intraday.build()
    report = scan.get(symbol)
    if report is None:
        raise HTTPException(404, "Unknown symbol, or no intraday data yet - refresh on the Intraday page")
    ctx = {"r": report, "status": scan.status, "chart": intraday.chart_payload(report), "nav": "intraday"}
    return templates.TemplateResponse(request, "intraday_stock.html", ctx)


# ---------- order desk: every signal for one stock, plus a (dry-run) order ticket ----------

DESK_CAPITAL, DESK_RISK = 100_000, 1.0   # the sizer's defaults; the browser can change them per request
Mode = Literal["swing", "intraday"]


def _desk_report(symbol: str, mode: Mode):
    report = (analysis.build() if mode == "swing" else intraday.build()).get(symbol)
    if report is None:
        raise HTTPException(404, f"No {mode} analysis for {symbol}: refresh the data first")
    return report


def _draft(symbol: str, mode: Mode, capital: float, risk: float, qty: int | None) -> desk.Draft:
    report = _desk_report(symbol, mode)
    ref = desk.swing_reference(symbol) if mode == "swing" else desk.intraday_reference(report)
    return desk.build_draft(mode, symbol, report, ref, capital, risk, qty)


def _signal_rows(report) -> list[dict]:
    records = signal_record.records()
    return [{"s": s, "pillar": label, "record": records.get(s.name), "evidence": signal_record.describe(records.get(s.name))}
            for label, _, signals in report.pillars for s in signals]


def _order_cards(symbol: str, report) -> list[dict]:
    cards = [{"mode": "swing", "title": f"Swing order (delivery, up to {SWING_MAX_HOLD} sessions)", "verdict": report.verdict,
              "draft": _draft(symbol, "swing", DESK_CAPITAL, DESK_RISK, None), "plan": report.plan, "why": report.blockers}]
    live = intraday.build().get(symbol)
    if live is not None:
        plan = live.best.plan if live.best else None
        cards.append({"mode": "intraday", "title": "Intraday order (same day, flat by " + f"{SQUARE_OFF:%H:%M})",
                      "verdict": live.verdict, "draft": _draft(symbol, "intraday", DESK_CAPITAL, DESK_RISK, None),
                      "plan": plan, "why": [live.reason]})
    return cards


@app.get("/desk", response_class=HTMLResponse)
def desk_page(request: Request, symbol: str = ""):
    result = analysis.build()
    report = result.get(symbol) if symbol else (result.reports[0] if result.reports else None)
    if report is None:
        raise HTTPException(404, "Unknown symbol, or no data yet - hit Refresh on the dashboard")
    rows = _signal_rows(report)
    proven = sum(1 for row in rows if row["record"] and row["record"]["status"] == "edge")
    tested = sum(1 for row in rows if row["record"] and row["record"]["status"] != "insufficient")
    ctx = {"r": report, "rows": rows, "proven": proven, "tested": tested, "cards": _order_cards(report.symbol, report),
           "orders": desk.recent_orders(), "nav": "desk", "bar": signal_record.bar(),
           "stocks": [(r.symbol, r.name, r.verdict) for r in result.reports], "capital": DESK_CAPITAL, "risk": DESK_RISK}
    partial = request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request")
    return templates.TemplateResponse(request, "_desk_panel.html" if partial else "desk.html", ctx)


@app.get("/desk/ticket", response_class=HTMLResponse)
def desk_ticket(request: Request, symbol: str, mode: Mode, capital: float = DESK_CAPITAL, risk: float = DESK_RISK,
                qty: int | None = None):
    draft = _draft(symbol, mode, capital, risk, qty)
    return templates.TemplateResponse(request, "_ticket.html", {"d": draft, "capital": capital})


@app.post("/desk/order", response_class=HTMLResponse)
def desk_order(request: Request, symbol: str, mode: Mode, capital: float = DESK_CAPITAL, risk: float = DESK_RISK,
               qty: int | None = None):
    if not request.headers.get("HX-Request"):   # a cross-site form cannot set this header
        raise HTTPException(403, "Orders can only be recorded from the desk page")
    ctx = {"orders": None, "row": None, "error": ""}
    try:
        ctx["row"] = desk.record(_draft(symbol, mode, capital, risk, qty), datetime.now())
    except desk.OrderRefused as exc:   # 200 on purpose: htmx does not swap 4xx responses
        ctx["error"] = str(exc)
    ctx["orders"] = desk.recent_orders()
    return templates.TemplateResponse(request, "_order_result.html", ctx)


# ---------- research & validation ----------

@app.get("/research", response_class=HTMLResponse)
def research_page(request: Request):
    news = data.load_result("news") or {}
    scored = sorted(((s, v) for s, v in news.get("stocks", {}).items() if v["status"] == "ok"),
                    key=lambda item: item[1]["score"])
    ctx = {"nav": "research", "bt": data.load_result("backtest"), "news": news, "ml": data.load_result("model"),
           "study": data.load_result("sentiment_study"), "ib": data.load_result("intraday_backtest"),
           "fw": data.load_result("forward"),
           "ml_note": analysis.build().ml_note, "names": STOCKS, "proba_gate": PROBA_GATE,
           "news_low": scored[:5], "news_high": scored[::-1][:5]}
    return templates.TemplateResponse(request, "research.html", ctx)


# ---------- background refresh jobs ----------

def _job(name: str) -> RefreshJob:
    if name not in jobs:
        raise HTTPException(404, "Unknown job")
    return jobs[name]


def _status(request: Request, name: str) -> HTMLResponse:
    status = _job(name).snapshot()
    response = templates.TemplateResponse(request, "_refresh_status.html", {"s": status, "name": name})
    if status.state == "done":
        response.headers["HX-Refresh"] = "true"  # new data -> reload the page
    return response


@app.post("/refresh/{name}", response_class=HTMLResponse)
def refresh(request: Request, name: str):
    _job(name).start()  # no-op if already running; either way we report live status
    return _status(request, name)


@app.get("/refresh/{name}/status", response_class=HTMLResponse)
def refresh_status(request: Request, name: str):
    return _status(request, name)
