"""The active market for this process. One engine, one profile per market; pick with STOCK_PICKER_MARKET.

    STOCK_PICKER_MARKET=india   (default) NSE large caps
    STOCK_PICKER_MARKET=us      NYSE/Nasdaq large caps

One process trades one market: run two servers for both (./serve.sh, ./serve.sh us). Each market has its own data
directory, research ledgers and forward-test files, so their evidence can never mix.
"""

import os

from app.market.profile import Market

MARKET_ENV = "STOCK_PICKER_MARKET"


def _load(key: str) -> Market:
    if key == "india":
        from app.market.india import MARKET as india
        return india
    if key == "us":
        from app.market.us import MARKET as us
        return us
    raise ValueError(f"{MARKET_ENV}={key!r}: expected 'india' or 'us'")


MARKET: Market = _load(os.environ.get(MARKET_ENV, "india").strip().lower())
