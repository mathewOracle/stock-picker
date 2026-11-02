"""The active market for this process. One engine, one profile per market; pick with STOCK_PICKER_MARKET.

    STOCK_PICKER_MARKET=india   (default) NSE large caps
    STOCK_PICKER_MARKET=us      NYSE/Nasdaq large caps
    STOCK_PICKER_MARKET=crypto  the largest coins, 24/7 (served by app/crypto/main.py)

One process trades one market. `./serve.sh` runs all of them behind one port (app/gateway.py: India / US / Crypto
tabs); `./serve.sh india`, `./serve.sh us` or `./serve.sh crypto` runs a single market. Each market has its own data
directory, research ledgers and forward-test files, so their evidence can never mix.
"""

import importlib
import os

from app.market.profile import Market

MARKET_ENV = "STOCK_PICKER_MARKET"
NAMES = ("india", "us", "crypto")   # every market, in tab order; the first is the default


def load(name: str | None) -> Market:
    """The profile for a market name ('india' when unset); anything unknown is an error, never a silent default."""
    key = (name or NAMES[0]).strip().lower()
    if key not in NAMES:
        raise ValueError(f"{MARKET_ENV}={name!r}: expected one of {', '.join(NAMES)}")
    return importlib.import_module(f"app.market.{key}").MARKET


MARKET: Market = load(os.environ.get(MARKET_ENV))
