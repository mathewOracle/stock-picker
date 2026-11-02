"""Crypto data: the shared Yahoo refresh (app/data.py) with a coin fetcher instead of company statements.

Prices, caching, retries and the proxy handling are app/data.py's; this module only knows which coin fields to keep,
and records a daily snapshot of every coin's circulating supply so supply inflation can be MEASURED over time
(free sources publish today's supply, not its history).
"""

from datetime import datetime, timezone

import yfinance as yf

from app import data

COIN_FIELDS = (
    "marketCap", "fullyDilutedValue", "circulatingSupply", "totalSupply", "maxSupply", "volume24Hr",
    "averageDailyVolume3Month", "allTimeHigh", "allTimeLow", "startDate", "firstTradeDateMilliseconds",
    "website", "whitepaper",
)
SUPPLY_RESULT = "supply"        # {symbol: {"YYYY-MM-DD": circulating supply}}


def fetch_coin(symbol: str, session) -> dict:
    """One coin's supply / valuation fields. Raises when Yahoo has nothing, so the refresh retries and reports it."""
    info = yf.Ticker(symbol, session=session).info
    if not info.get("marketCap"):
        raise ValueError(f"Yahoo returned no coin data for {symbol}")
    return {"info": {key: info.get(key) for key in COIN_FIELDS},
            "fetched": datetime.now(timezone.utc).date().isoformat()}


def record_supply(coins: list[data.StockData]) -> int:
    """Add each coin's latest circulating supply to the history, keyed by the day it was fetched. Returns how many."""
    history: dict[str, dict[str, float]] = data.load_result(SUPPLY_RESULT) or {}
    added = 0
    for coin in coins:
        day, supply = coin.fundamentals.get("fetched"), coin.fundamentals.get("info", {}).get("circulatingSupply")
        if day and supply and history.setdefault(coin.symbol, {}).get(day) != supply:
            history[coin.symbol][day] = supply
            added += 1
    if added:
        data.save_result(SUPPLY_RESULT, history)
    return added


def supply_history() -> dict[str, dict[str, float]]:
    return data.load_result(SUPPLY_RESULT) or {}


def _quiet(done: int, total: int, label: str) -> None:
    pass


def refresh(progress: data.Progress = _quiet) -> data.RefreshResult:
    result = data.refresh(progress, fetch=fetch_coin)
    record_supply(data.load_stocks())
    return result


def refresh_symbol(symbol: str) -> data.RefreshResult:
    result = data.refresh_symbol(symbol, fetch=fetch_coin)
    record_supply([c for c in data.load_stocks() if c.symbol == symbol])
    return result
