"""What a market IS to this app: universe, clock, costs, money units, news locale. Data only, no behaviour.

Every engine module (indicators, scoring, backtests, ML, desk) is market-agnostic and reads the active profile
from `app.market.MARKET`. Adding a market = adding one profile module; nothing else forks.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]


def shift(t: time, minutes: int) -> time:
    """A wall-clock time moved by `minutes` (session maths never crosses midnight)."""
    return (datetime.combine(date.min, t) + timedelta(minutes=minutes)).time()


@dataclass(frozen=True)
class Clock:
    """Regular cash-session hours in the exchange's own time zone. Yahoo bars arrive in this wall-clock time."""
    tz: ZoneInfo
    open: time
    close: time
    early_label: str             # what the hours just before the open are called (NSE pre-open auction, US pre-market)
    early_start: time            # when those hours begin
    opening_range_minutes: int = 15
    last_entry_before_close: int = 45   # no new intraday entries this many minutes before the close
    square_off_before_close: int = 15   # our own intraday time exit, this many minutes before the close

    @property
    def opening_range_end(self) -> time:
        return shift(self.open, self.opening_range_minutes)

    @property
    def no_new_entries(self) -> time:
        return shift(self.close, -self.last_entry_before_close)

    @property
    def square_off(self) -> time:
        return shift(self.close, -self.square_off_before_close)

    @property
    def settled_after(self) -> time:
        """Daily closing prices are treated as final this long after the close (Yahoo lags)."""
        return shift(self.close, 30)


@dataclass(frozen=True)
class Session:
    """One trading day's actual hours (half-days close early)."""
    open: time
    close: time


@dataclass(frozen=True)
class News:
    locale: str                  # Google News RSS query-string locale, e.g. "hl=en-US&gl=US&ceid=US:en"
    finance_terms: str           # appended to every query so headlines are about the stock, not the word
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Money:
    symbol: str                  # "₹", "$"
    big_divisor: float           # 1e7 (crore), 1e6 (million): the unit traded-value metrics are stored in
    big_label: str               # "Cr", "M"
    steps: tuple[tuple[float, str], ...] = ()   # US: T/B/M, three significant figures; empty = always big_label

    def big(self, value: float) -> str:
        """A large amount in the market's habitual unit: ₹1,234 Cr / $3.90T, $452B, $25.0M."""
        if self.steps:
            size, label = next(((s, lb) for s, lb in self.steps if abs(value) >= s), self.steps[-1])
            n = value / size
            return f"{self.symbol}{n:,.{2 if abs(n) < 10 else 1 if abs(n) < 100 else 0}f}{label}"
        sep = " " if len(self.big_label) > 1 else ""
        return f"{self.symbol}{value / self.big_divisor:,.0f}{sep}{self.big_label}"

    def big_units(self, value: float) -> str:
        """An amount ALREADY in big units (e.g. a traded-value metric)."""
        if self.steps:
            return self.big(value * self.big_divisor)
        sep = " " if len(self.big_label) > 1 else ""
        return f"{self.symbol}{value:,.0f}{sep}{self.big_label}"


@dataclass(frozen=True)
class Wording:
    """How this market's brokers name the order types the entry/exit steps describe."""
    intraday_product: str        # "intraday (MIS) product"
    swing_product: str           # "the delivery (CNC) product"
    swing_exit_order: str        # "a GTT OCO order (good-till-triggered, one-cancels-the-other)"
    swing_exit_why: str          # why that order type and not a plain stop
    adviser: str                 # who to talk to before investing, in this jurisdiction
    costs_detail: str            # what the per-side cost assumption covers
    forward_why: str             # why momentum is forward-tested in this market (research narrative, HTML-safe)
    forward_rules: str           # where its pre-registered rules live
    short_verb: str = "short-sell"


@dataclass(frozen=True)
class Market:
    key: str
    app_name: str
    exchange: str                # shown in copy: "NSE", "NYSE/Nasdaq"
    regulator: str               # shown in the disclaimer: "SEBI", "SEC/FINRA"
    clock: Clock
    stocks: dict[str, str]
    indices: dict[str, str]
    benchmark: str
    benchmark_name: str          # "Nifty", "S&P 500"
    vix: str
    vix_name: str
    money: Money
    swing_cost_per_side: float   # brokerage + taxes + fees + slippage, deliberately conservative
    intraday_cost_per_side: float
    min_traded_value: float      # intraday liquidity floor, in money.big units per day
    news: News
    u2_candidates: tuple[str, ...]   # the forward test's independent universe (frozen per market)
    broker_name: str             # whose order format the dry-run tickets use
    wording: Wording
    symbol_suffix: str = ""      # Yahoo suffix hidden in the UI (".NS")
    data_subdir: str = "data"
    docs_subdir: str = "docs"
    default_port: int = 61287

    @property
    def data_dir(self) -> Path:
        return ROOT / self.data_subdir

    @property
    def docs_dir(self) -> Path:
        return ROOT / self.docs_subdir

    def short_symbol(self, symbol: str) -> str:
        return symbol.removesuffix(self.symbol_suffix) if self.symbol_suffix else symbol

    @property
    def broker_label(self) -> str:
        """Who the dry run is NOT sending to, in a sentence: a named broker, or 'a broker' while none is chosen."""
        return "a broker" if self.broker_name == "broker-neutral" else self.broker_name

    def session(self, day: date) -> Session | None:
        """The day's hours, or None if the exchange is shut. Default: regular hours Mon-Fri (holidays unknown)."""
        return Session(self.clock.open, self.clock.close) if day.weekday() < 5 else None

    @property
    def knows_holidays(self) -> bool:
        return False
