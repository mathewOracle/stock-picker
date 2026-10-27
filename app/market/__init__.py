"""The active market for this process. One engine, one profile per market; pick with STOCK_PICKER_MARKET.

    STOCK_PICKER_MARKET=india   (default) NSE large caps
    STOCK_PICKER_MARKET=us      NYSE/Nasdaq large caps

One process trades one market. `./serve.sh` runs both behind one port (app/gateway.py: India / US tabs);
`./serve.sh india` or `./serve.sh us` runs a single market. Each market has its own data directory, research ledgers
and forward-test files, so their evidence can never mix.
"""

import os

from app.market.profile import Market

MARKET_ENV = "STOCK_PICKER_MARKET"
NAMES = ("india", "us")   # every market, in tab order; the first is the default


def load(name: str | None) -> Market:
    """The profile for a market name ('india' when unset); anything unknown is an error, never a silent default."""
    key = (name or NAMES[0]).strip().lower()
    if key == "india":
        from app.market.india import MARKET as india
        return india
    if key == "us":
        from app.market.us import MARKET as us
        return us
    raise ValueError(f"{MARKET_ENV}={name!r}: expected 'india' or 'us'")


MARKET: Market = load(os.environ.get(MARKET_ENV))
