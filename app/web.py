"""Template filters and the refresh-job routes every market's web app shares (stocks: app/main.py, coins: app/crypto/main.py)."""

import math
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.intraday.economics import describe_evidence
from app.jobs import RefreshJob
from app.market import MARKET
from app.prices import price_text


def _is_nan(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def pct(value, signed: bool = True, digits: int = 1) -> str:
    return "–" if _is_nan(value) else f"{value * 100:{'+' if signed else ''}.{digits}f}%"


def num(value, digits: int = 1) -> str:
    return "–" if _is_nan(value) else f"{value:,.{digits}f}"


def price(value) -> str:
    """A price that stays readable from $100,000 down to $0.000005: 2 decimals, or 4 significant figures below 1."""
    return "–" if _is_nan(value) else price_text(value, digits=2, sig=4)


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


FILTERS = dict(pct=pct, num=num, price=price, pe=pe, money_big=money_big, money_units=money_units, timestamp=timestamp,
               evidence_note=describe_evidence, short_symbol=MARKET.short_symbol)


def refresh_router(jobs: dict[str, RefreshJob], templates: Jinja2Templates) -> APIRouter:
    """POST /refresh/{name} starts a background job; GET .../status polls it (the page reloads when it is done)."""
    router = APIRouter()

    def job(name: str) -> RefreshJob:
        if name not in jobs:
            raise HTTPException(404, "Unknown job")
        return jobs[name]

    def status(request: Request, name: str) -> HTMLResponse:
        snapshot = job(name).snapshot()
        response = templates.TemplateResponse(request, "_refresh_status.html", {"s": snapshot, "name": name})
        if snapshot.state == "done":
            response.headers["HX-Refresh"] = "true"  # new data -> reload the page
        return response

    @router.post("/refresh/{name}", response_class=HTMLResponse)
    def refresh(request: Request, name: str):
        job(name).start()  # no-op if already running; either way we report live status
        return status(request, name)

    @router.get("/refresh/{name}/status", response_class=HTMLResponse)
    def refresh_status(request: Request, name: str):
        return status(request, name)

    return router
