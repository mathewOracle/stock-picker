"""FastAPI app: the order desk (home), market overview, stock deep-dives, intraday scanner, research and refresh jobs."""

import math
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import analysis, data, deskview, marketview
from app.broker import desk
from app.intraday import analysis as intraday
from app.intraday import archive as intraday_archive
from app.intraday.checks import MIN_ATR_PCT, MIN_TRADED_VALUE
from app.intraday.indicators import NO_NEW_ENTRIES, SQUARE_OFF
from app.intraday.setups import PLAYBOOKS
from app.jobs import RefreshJob
from app.market import MARKET, NAMES as MARKET_NAMES, load as load_market
from app.research import pipeline, u2
from app.research.backtest import MAX_HOLD as SWING_MAX_HOLD
from app.research.ml import PROBA_GATE
from app.scoring import BUY_LEVELS, GATES, PILLAR_WEIGHTS, VERDICTS, WATCHLIST
from app.universe import STOCKS

BASE = Path(__file__).resolve().parent
app = FastAPI(title=MARKET.app_name)
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


def money_big(value) -> str:
    """A large amount (market cap) in the market's habitual unit: ₹1,234 Cr / $1,234M."""
    return "–" if _is_nan(value) else MARKET.money.big(value)


def money_units(value) -> str:
    """An amount already in big units (the traded-value metric)."""
    return "–" if _is_nan(value) else MARKET.money.big_units(value)


def timestamp(value) -> str:
    return "never" if value is None else datetime.fromtimestamp(value).strftime("%d %b %Y, %H:%M")


def session_state() -> dict:
    """The exchange's phase right now, for the live dot in the header (holidays and half-days included)."""
    label, is_open, _ = intraday.market_phase(datetime.now(MARKET.clock.tz))
    return {"label": label, "open": is_open}


templates.env.filters.update(pct=pct, num=num, pe=pe, money_big=money_big, money_units=money_units, timestamp=timestamp,
                              short_symbol=MARKET.short_symbol, evidence_note=intraday.describe_evidence)
templates.env.globals.update(square_off=f"{SQUARE_OFF:%H:%M}", no_new_entries=f"{NO_NEW_ENTRIES:%H:%M}",
                             swing_max_hold=SWING_MAX_HOLD,  # the swing backtest's time exit, in sessions
                             long_bias=intraday.LONG_BIAS, short_bias=intraday.SHORT_BIAS,
                             max_risk_pct=desk.MAX_RISK_PCT,  # one source for the risk cap: forms and orders agree
                             market=MARKET, accounts=desk.ACCOUNTS, tz_label=intraday.tz_label,
                             u2_count=len(u2.SYMBOLS), session_state=session_state,
                             market_tabs=[load_market(name) for name in MARKET_NAMES])


# ---------- market overview (the old swing dashboard) ----------

@app.get("/market", response_class=HTMLResponse)
def dashboard(request: Request):
    result = analysis.build()
    ctx = {
        "a": result, "nav": "swing", "markets": marketview.page(result),
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
           "min_rr": intraday.MIN_RR, "min_value": MIN_TRADED_VALUE, "min_atr": MIN_ATR_PCT,
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


# ---------- order desk: the home page ----------

Mode = Literal["swing", "intraday"]
Rank = Literal["long", "short"]


def _is_partial(request: Request) -> bool:
    """HTMX swaps get a fragment; a full page load (or history restore) gets the whole page."""
    return bool(request.headers.get("HX-Request")) and not request.headers.get("HX-History-Restore-Request")


def _require_htmx(request: Request) -> None:
    if not request.headers.get("HX-Request"):   # a cross-site form cannot set this header
        raise HTTPException(403, "This action only works from the order desk page")


@app.get("/", response_class=HTMLResponse)
def desk_page(request: Request, tab: Mode = "swing", symbol: str = "", rank: Rank = "long"): 
    try:
        ctx = deskview.page_context(tab, symbol, rank)
    except deskview.UnknownSymbol:
        raise HTTPException(404, f"Unknown symbol {symbol}")
    return templates.TemplateResponse(request, "_desk.html" if _is_partial(request) else "desk.html", {**ctx, "nav": "desk"})


@app.get("/desk")
def desk_legacy(request: Request):
    """The order desk used to live at /desk; keep old links working."""
    return RedirectResponse("/?" + request.url.query if request.url.query else "/", status_code=307)


def _detail(request: Request, tab: Mode, symbol: str, notice: dict | None = None, template: str | None = None):
    try:
        report = deskview.report_for(symbol, tab)
    except deskview.NoAnalysis as exc:
        raise HTTPException(404, str(exc))
    ctx = {**deskview.detail_context(tab, report), "notice": notice}
    if template:   # a re-analysis also refreshes the stock's row in the list (out-of-band)
        ctx["row"] = deskview.row_for(tab, symbol)
    return templates.TemplateResponse(request, template or f"_detail_{tab}.html", ctx)


@app.get("/detail", response_class=HTMLResponse)
def desk_detail(request: Request, tab: Mode, symbol: str):
    return _detail(request, tab, symbol)


@app.post("/reanalyse", response_class=HTMLResponse)
def desk_reanalyse(request: Request, tab: Mode, symbol: str):
    """Re-download one stock's data and recompute it. Failures keep the old data and say so (200: htmx won't swap a 4xx)."""
    _require_htmx(request)
    if symbol not in STOCKS:
        raise HTTPException(404, f"Unknown symbol {symbol}")
    refresh = data.refresh_symbol if tab == "swing" else intraday_archive.refresh_symbol
    try:
        refresh(symbol)
        notice = {"ok": True, "text": f"Re-analysed {STOCKS[symbol]} at {datetime.now():%H:%M}: fresh data downloaded and every signal recomputed."}
    except Exception as exc:   # Yahoo fails in many ways; whatever happened, the cache is untouched
        notice = {"ok": False, "text": f"Re-analysis failed: {exc or type(exc).__name__}. Showing the previous data."}
    return _detail(request, tab, symbol, notice, template="_reanalysed.html")


@app.get("/desk/ticket", response_class=HTMLResponse)
def desk_ticket(request: Request, symbol: str, mode: Mode, capital: float = deskview.DESK_CAPITAL, risk: float = deskview.DESK_RISK,
                qty: int | None = None, account: str = ""):
    try:
        draft = deskview.draft(symbol, mode, capital, risk, qty, account=account)
    except deskview.NoAnalysis as exc:
        raise HTTPException(404, str(exc))
    return templates.TemplateResponse(request, "_ticket.html", {"d": draft, "capital": capital})


@app.post("/desk/order", response_class=HTMLResponse)
def desk_order(request: Request, symbol: str, mode: Mode, capital: float = deskview.DESK_CAPITAL, risk: float = deskview.DESK_RISK,
               qty: int | None = None, account: str = ""):
    _require_htmx(request)
    ctx = {"orders": None, "row": None, "error": ""}
    try:
        if (fresh := deskview.symbol_freshness(symbol, mode))["stale"]:   # never build an order on old prices
            raise desk.OrderRefused(fresh["why"])
        ctx["row"] = desk.record(deskview.draft(symbol, mode, capital, risk, qty, account=account), deskview.now())
    except deskview.NoAnalysis as exc:
        raise HTTPException(404, str(exc))
    except desk.OrderRefused as exc:   # 200 on purpose: htmx does not swap 4xx responses
        ctx["error"] = str(exc)
    ctx["orders"] = desk.recent_orders()
    ctx["card"] = deskview.order_card(symbol, mode, deskview.report_for(symbol, mode))   # the card flips to "already recorded" in place
    return templates.TemplateResponse(request, "_order_result.html", ctx)


# ---------- research & validation ----------

def _research_context() -> dict:
    news = data.load_result("news") or {}
    scored = sorted(((s, v) for s, v in news.get("stocks", {}).items() if v["status"] == "ok"),
                    key=lambda item: item[1]["score"])
    return {"bt": data.load_result("backtest"), "news": news, "ml": data.load_result("model"),
            "study": data.load_result("sentiment_study"), "ib": data.load_result("intraday_backtest"),
            "fw": data.load_result("forward"),
            "ml_note": analysis.build().ml_note, "names": STOCKS, "proba_gate": PROBA_GATE,
            "news_low": scored[:5], "news_high": scored[::-1][:5]}


@app.get("/research", response_class=HTMLResponse)
def research_page(request: Request):
    return templates.TemplateResponse(request, "research.html", {**_research_context(), "nav": "research"})


@app.get("/research/{scope}", response_class=HTMLResponse)
def research_panel(request: Request, scope: Mode):
    """The evidence for ONE side of the desk (swing or intraday), shown in a panel on that tab."""
    return templates.TemplateResponse(request, "_research_drawer.html", {**_research_context(), "scope": scope})


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
