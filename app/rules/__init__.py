"""Market rules the order desk and the intraday engine must respect, as Check objects. Rules are per market.

A Check is `ok` (rule satisfied, said out loud), `info` (something you must know), `warn` (allowed, but risky) or
`block` (the desk will not record the order, and the ticket says why). India has no rule module yet: its desk keeps
its existing behaviour. The US rules live in app/rules/us.py.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from app.market import MARKET

STATUSES = ("ok", "info", "warn", "block")


@dataclass(frozen=True)
class Check:
    rule: str        # the rule's citation, e.g. "FINRA Rule 4210 (pattern day trader)"
    status: str      # one of STATUSES
    message: str     # what it means for THIS order, in plain words

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"unknown check status {self.status!r}")


@dataclass(frozen=True)
class DeskContext:
    """Everything a market's rules need to judge one order. Built by the desk; rules never read files or clocks."""
    mode: str                         # "swing" | "intraday"
    symbol: str
    direction: int                    # +1 long, -1 short
    qty: int
    ref_price: float
    account: str                      # "margin" | "cash"
    capital: float                    # account equity the user entered
    now: datetime                     # in the exchange's time zone
    journal: tuple[dict, ...] = ()    # every dry-run order recorded so far
    earnings: date | None = None      # next earnings date, if known
    hold_sessions: int = 0            # swing time exit, in sessions
    rule201: bool | None = None       # intraday only: is the short-sale circuit breaker active right now?
    restricted: frozenset[str] = field(default_factory=frozenset)

    @property
    def notional(self) -> float:
        return self.qty * self.ref_price


def blocking(checks: list[Check] | tuple[Check, ...]) -> Check | None:
    return next((c for c in checks if c.status == "block"), None)


def accounts() -> tuple[str, ...]:
    """Account types the ticket asks about (none where the market's rules don't depend on it)."""
    return ("margin", "cash") if MARKET.key == "us" else ()


def desk_checks(ctx: DeskContext) -> list[Check]:
    if MARKET.key == "us":
        from app.rules import us
        return us.desk_checks(ctx)
    return []


def intraday_block(bars: pd.DataFrame, side: str) -> str:
    """Why a market rule forbids OPENING this intraday trade on the bar that just closed ('' = allowed).

    One function for the live verdict and the intraday backtest, so the backtest never counts a trade the desk
    would refuse. `bars` must end at the decision bar (no lookahead).
    """
    if MARKET.key == "us" and side == "Short":
        from app.rules import us
        if us.rule201_active(bars):
            return us.RULE201_BLOCK
    return ""
