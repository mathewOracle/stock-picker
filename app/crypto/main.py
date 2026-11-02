"""FastAPI app for the crypto market: the coin overview (home), coin deep-dives and the data refresh.

Run with STOCK_PICKER_MARKET=crypto (the gateway does it for the Crypto tab). It reuses the stock app's templates,
static files, chart code and filters; it does not load the order desk, intraday scanner or research pipeline,
because those are built around an exchange session that crypto does not have.
"""

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.chartdata import chart_payload
from app.crypto import analysis, coindata
from app.crypto.tokenomics import HARD_FLAGS, MIN_SUPPLY_DAYS, PILLAR_WEIGHTS
from app.jobs import RefreshJob
from app.market import MARKET, NAMES as MARKET_NAMES, load as load_market
from app.scoring import BUY_LEVELS, GATES, VERDICTS
from app.universe import STOCKS
from app.web import FILTERS, refresh_router

if MARKET.key != "crypto":
    raise RuntimeError("app.crypto.main serves the crypto market: start it with STOCK_PICKER_MARKET=crypto")

BASE = Path(__file__).resolve().parents[1]
app = FastAPI(title=f"{MARKET.app_name} - Crypto")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
jobs = {"daily": RefreshJob(coindata.refresh)}


def session_state() -> dict:
    return {"label": "Trades 24/7", "open": True}   # no sessions, weekends or holidays


templates.env.filters.update(FILTERS)
templates.env.globals.update(market=MARKET, session_state=session_state,
                             market_tabs=[load_market(name) for name in MARKET_NAMES])


def _filtered(category: str, verdict: str) -> list[analysis.CoinReport]:
    return [r for r in analysis.build().reports
            if (not category or r.category == category) and (not verdict or r.verdict == verdict)]


@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    result = analysis.build()
    ctx = {"o": result, "nav": "coins", "reports": result.reports,
           "buys": [r for r in result.reports if r.verdict in BUY_LEVELS],
           "categories": sorted({r.category for r in result.reports}), "verdicts": VERDICTS,
           "gates": GATES, "weights": PILLAR_WEIGHTS, "hard_flags": sorted(HARD_FLAGS)}
    return templates.TemplateResponse(request, "crypto/overview.html", ctx)


@app.get("/table", response_class=HTMLResponse)
def table(request: Request, category: str = "", verdict: str = ""):
    return templates.TemplateResponse(request, "crypto/_table.html", {"reports": _filtered(category, verdict)})


@app.get("/coin/{symbol}", response_class=HTMLResponse)
def coin(request: Request, symbol: str):
    report = analysis.build().get(symbol)
    if report is None:
        raise HTTPException(404, "Unknown coin, or no data yet - hit Refresh on the overview")
    ctx = {"r": report, "chart": chart_payload(symbol, report), "weights": PILLAR_WEIGHTS, "nav": "coins",
           "supply_days_needed": MIN_SUPPLY_DAYS}
    return templates.TemplateResponse(request, "crypto/coin.html", ctx)


@app.post("/coin/{symbol}/refresh", response_class=HTMLResponse)
def coin_refresh(request: Request, symbol: str):
    """Re-download one coin (and Bitcoin, for relative strength) right now. A failure keeps the old data and says so."""
    if not request.headers.get("HX-Request"):   # a cross-site form cannot set this header
        raise HTTPException(403, "This action only works from the coin page")
    if symbol not in STOCKS:
        raise HTTPException(404, f"Unknown coin {symbol}")
    try:
        coindata.refresh_symbol(symbol)
        notice = {"ok": True, "text": f"Re-analysed {STOCKS[symbol]} at {datetime.now():%H:%M}."}
    except Exception as exc:   # Yahoo fails in many ways; whatever happened, the cache is untouched
        notice = {"ok": False, "text": f"Re-analysis failed: {exc or type(exc).__name__}. Showing the previous data."}
    response = templates.TemplateResponse(request, "crypto/_notice.html", {"notice": notice})
    if notice["ok"]:
        response.headers["HX-Refresh"] = "true"
    return response


# Links shared with the stock app (header nav, old bookmarks) land on the coin overview.
@app.get("/market")
@app.get("/desk")
@app.get("/intraday")
@app.get("/research")
def to_overview():
    return RedirectResponse("/", status_code=307)


@app.get("/stock/{symbol}")
def stock_to_coin(symbol: str):
    return RedirectResponse(f"/coin/{symbol}", status_code=307)


app.include_router(refresh_router(jobs, templates))
