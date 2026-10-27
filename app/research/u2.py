"""U2: the forward test's independent universe, frozen per market in its profile (app/market/<market>.py).

India: Addendum A of docs/SWING_RESEARCH_PLAN.md, frozen 2026-10-23. US: docs/us/SWING_RESEARCH_PLAN.md, frozen
2026-10-27. Names already in the live universe (app.universe.STOCKS) are removed in code. Bars live in the market's
data dir under research/extra_history/ (git-ignored), never in the app's own cache, and only ever grow (data.top_up).
"""

import os
import time
from pathlib import Path

import pandas as pd

from app import data
from app.market import MARKET
from app.universe import STOCKS

SYMBOLS = sorted(set(MARKET.u2_candidates) - set(STOCKS))
OUT = data.DB_PATH.parent / "research" / "extra_history"
BATCH, PAUSE, ATTEMPTS = 20, 5, 3


def path(symbol: str) -> Path:
    return OUT / f"{symbol.replace('&', '_')}.csv.gz"


def load(symbol: str) -> pd.DataFrame | None:
    p = path(symbol)
    return pd.read_csv(p, index_col=0, parse_dates=True) if p.exists() else None


def _save(symbol: str, frame: pd.DataFrame) -> None:
    tmp = path(symbol).with_suffix(".tmp.gz")
    frame.to_csv(tmp)
    os.replace(tmp, path(symbol))          # never a half-written series


def refresh(progress: data.Progress = data._no_progress) -> list[str]:
    """Top up every U2 series (first run: 10 years). Returns the symbols Yahoo did not return."""
    OUT.mkdir(parents=True, exist_ok=True)
    session, updated = data._fresh_session(), set()
    batches = [SYMBOLS[i: i + BATCH] for i in range(0, len(SYMBOLS), BATCH)]
    for n, batch in enumerate(batches, start=1):
        stored = {s: load(s) for s in batch}
        for attempt in range(ATTEMPTS):
            if merged := data.top_up(stored, session):
                break
            time.sleep(PAUSE * (attempt + 2))        # Yahoo rate-limits the shared proxy (HTTP 429)
        for symbol, frame in merged.items():
            _save(symbol, frame)
        updated |= set(merged)
        progress(n, len(batches), f"U2 prices, batch {n}")
        time.sleep(PAUSE if n < len(batches) else 0)
    if not updated:
        raise data.RefreshError("Could not download any U2 prices from Yahoo Finance. Check VPN/proxy.")
    return sorted(set(SYMBOLS) - updated)
