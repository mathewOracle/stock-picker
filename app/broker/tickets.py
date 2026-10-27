"""Broker-agnostic order maths: sizing, the tick grid, the backtests' skip rules, and the price legs of a validated plan.

Every broker format (angelone.py for India, neutral.py for the US) turns the SAME Legs into its own request bodies, so
a plan is traded identically whichever market runs it:

* enter with a marketable LIMIT at most ENTRY_SLIPPAGE beyond the reference, never at or past T1;
* skip if the reference is at/beyond the stop or T1 (the backtests do not enter a trade that is already decided);
* exits for the whole quantity: a stop (trigger + limit STOP_LIMIT_BUFFER beyond it) and a T1 limit.

Nothing here decides WHAT to trade: a ticket only exists for the app's final validated verdict.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from app.scoring import BUY_LEVELS

INTRADAY_SETUPS = ("Long setup", "Short setup")            # the only intraday verdicts backed by the backtest
ENTRY_SLIPPAGE = 0.005    # entries/exits are marketable LIMITs: at most 0.5% worse than the reference, never a bare MARKET
STOP_LIMIT_BUFFER = 0.02  # a triggered stop becomes a LIMIT up to 2% beyond the trigger, so it still fills in a fast move


@dataclass(frozen=True)
class Legs:
    """The prices of one trade, already on the tick grid. Broker modules format these; nothing recomputes them."""
    direction: int          # +1 long, -1 short
    qty: int
    entry: Decimal          # marketable entry limit
    stop_trigger: Decimal
    stop_limit: Decimal
    target_trigger: Decimal  # where a trigger-based target (GTT) fires
    target: Decimal          # target limit price

    @property
    def side(self) -> str:
        return "BUY" if self.direction > 0 else "SELL"

    @property
    def exit_side(self) -> str:
        return "SELL" if self.direction > 0 else "BUY"


@dataclass(frozen=True)
class Ticket:
    """Everything needed to trade one plan. `entry is None` means: don't trade, and `skip` says why."""
    entry: dict | None = None
    exits: tuple[dict, ...] = ()   # broker bodies, sent AFTER the entry fills
    time_exit: str = ""            # when to cancel the exits and flatten
    skip: str = ""
    legs: Legs | None = None       # the same prices, broker-neutral (what the ticket screen shows)
    product: str = ""              # human label for side/product, e.g. "DELIVERY" or "regular session, day order"
    exits_note: str = ""           # how the exits are sent, in plain words


def to_tick(price: float, tick: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    """Snap a price onto the exchange's tick grid (orders off the grid are rejected)."""
    return (Decimal(str(price)) / tick).to_integral_value(rounding) * tick


def position_size(capital: float, risk_pct: float, entry: float, stop: float) -> int:
    """Shares so a stop-out loses capital x risk%, capped at what capital buys (no leverage).

    Mirrors positionSize() in app/static/position-size.js; tests/test_broker_angelone.py pins the same cases.
    """
    per_share = abs(entry - stop)
    risk_qty = int(capital * risk_pct / 100 // per_share) if per_share > 0 else 0
    affordable = int(capital // entry) if entry > 0 else 0
    return min(risk_qty, affordable)


def marketable(ref: float, direction: int, tick: Decimal) -> Decimal:
    """Worst price we accept when crossing the spread: ENTRY_SLIPPAGE beyond `ref`, rounded away from the market."""
    return to_tick(ref * (1 + direction * ENTRY_SLIPPAGE), tick, ROUND_CEILING if direction > 0 else ROUND_FLOOR)


def entry_limit(ref: float, target: float, direction: int, tick: Decimal) -> Decimal:
    """Marketable entry, but never at or past T1: the backtest doesn't enter a trade that is already done."""
    limit = marketable(ref, direction, tick)
    if direction > 0:
        return min(limit, to_tick(target, tick, ROUND_CEILING) - tick)
    return max(limit, to_tick(target, tick, ROUND_FLOOR) + tick)


def skip_reason(ref: float, stop: float, target: float, qty: int, label: str) -> str:
    if qty < 1:
        return "quantity is 0: the stop is too wide for this capital and risk"
    if not min(stop, target) < ref < max(stop, target):
        return f"{label} {ref:,.2f} is at or beyond the stop {stop:,.2f} or T1 {target:,.2f}: the backtest skips it"
    return ""


def legs(plan, qty: int, ref: float, tick: Decimal) -> Legs:
    """The plan's prices on the tick grid. Exit limits round away from the market so they still fill."""
    direction = plan.direction
    away = ROUND_FLOOR if direction > 0 else ROUND_CEILING
    return Legs(direction, qty, entry_limit(ref, plan.target1, direction, tick),
                stop_trigger=to_tick(plan.stop, tick),
                stop_limit=to_tick(plan.stop * (1 - direction * STOP_LIMIT_BUFFER), tick, away),
                target_trigger=to_tick(plan.target1, tick),
                target=to_tick(plan.target1, tick, away))


def swing_gate(report, qty: int, open_price: float) -> str:
    """Why a swing ticket must not exist ('' = it may). Swing is long-only: a validated Buy, entered after the open."""
    if report.verdict not in BUY_LEVELS:
        return f"verdict is {report.verdict}: only a validated Buy is traded"
    return skip_reason(open_price, report.plan.stop, report.plan.target1, qty, "opened at")


def intraday_gate(report, qty: int, ltp: float) -> str:
    """Why an intraday ticket must not exist ('' = it may): a backtest-supported setup, priced inside its plan."""
    if report.verdict not in INTRADAY_SETUPS or report.best is None:
        return f"verdict is {report.verdict}: only a backtest-supported setup is traded"
    p = report.best.plan
    return skip_reason(ltp, p.stop, p.target1, qty, "price")
