"""Angel One SmartAPI order parameters for the app's validated swing and intraday plans.

Pure functions: no network, no SDK import, no credentials. They turn a plan the app has ALREADY validated into the
exact request bodies that smartapi-python's `SmartConnect.placeOrderFullResponse` and `gttCreateRule` expect, and
they trade the plan exactly as the backtests do:

* swing (app/research/backtest.py): enter at the next open with DELIVERY, skip if it opens at/beyond the stop or T1;
  a SELL GTT at the stop and one at T1 for the whole quantity; sell at session MAX_HOLD if neither triggered.
* intraday (app/research/intraday_backtest.py): enter at the next bar with INTRADAY, skip if price is at/beyond the
  stop or T1; a stop-loss order and a T1 limit for the whole quantity, placed after the fill; flat by SQUARE_OFF.

Nothing here decides WHAT to trade: a ticket is refused unless the app's final verdict is a validated Buy / setup.
Field names and values follow smartapi-python 1.5.5 (see docs/ANGELONE_ORDERS.md for the evidence and caveats).
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from app.intraday.indicators import SQUARE_OFF
from app.research.backtest import MAX_HOLD
from app.scoring import BUY_LEVELS

EXCHANGE = "NSE"
SWING_PRODUCT, INTRADAY_PRODUCT = "DELIVERY", "INTRADAY"   # Angel One's names for CNC and MIS
INTRADAY_SETUPS = ("Long setup", "Short setup")            # the only intraday verdicts backed by the backtest
ENTRY_SLIPPAGE = 0.005    # entries/exits are marketable LIMITs: at most 0.5% worse than the reference, never a bare MARKET
STOP_LIMIT_BUFFER = 0.02  # a triggered stop becomes a LIMIT up to 2% beyond the trigger, so it still fills in a fast move
GTT_DAYS = 2 * MAX_HOLD   # 40 sessions ~ 58 calendar days; doubled so holidays never expire a GTT before the time exit
_PAISE = Decimal("0.01")


@dataclass(frozen=True)
class Instrument:
    tradingsymbol: str    # "RELIANCE-EQ"
    token: str            # Angel One symboltoken
    tick: Decimal         # price step in rupees


@dataclass(frozen=True)
class Ticket:
    """Everything needed to trade one plan. `entry is None` means: don't trade, and `skip` says why."""
    entry: dict | None = None
    exits: tuple[dict, ...] = ()   # swing: gttCreateRule bodies; intraday: placeOrder bodies, sent AFTER the entry fills
    time_exit: str = ""            # when to cancel the exits and flatten with exit_now()
    skip: str = ""


def instrument(scrip_master: list[dict], symbol: str) -> Instrument:
    """The NSE cash-market row for an app symbol ('RELIANCE.NS'). Exactly one match, or an error: never guess.

    The scrip master lists the same name on NSE, BSE and F&O; matching on the name alone (as the old
    dividendAnalysis code did) can silently pick another exchange's token.
    """
    wanted = symbol.removesuffix(".NS") + "-EQ"
    rows = [r for r in scrip_master if r.get("exch_seg") == EXCHANGE and r.get("symbol") == wanted]
    if len(rows) != 1:
        raise LookupError(f"{len(rows)} NSE rows for {wanted} in the scrip master, expected exactly 1")
    tick = Decimal(str(rows[0]["tick_size"])) / 100    # the master gives paise: "5.000000" = Rs 0.05
    if tick <= 0:
        raise ValueError(f"bad tick size for {wanted}: {rows[0]['tick_size']!r}")
    return Instrument(wanted, str(rows[0]["token"]), tick)


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


# ---------- request bodies ----------

def _fmt(price: Decimal) -> str:
    return str(price.quantize(_PAISE))


def _order(inst: Instrument, side: str, product: str, qty: int, price: Decimal,
           trigger: Decimal | None = None) -> dict:
    """placeOrderFullResponse body. Strings throughout, like the SDK's own example."""
    body = {"variety": "NORMAL", "tradingsymbol": inst.tradingsymbol, "symboltoken": inst.token,
            "transactiontype": side, "exchange": EXCHANGE, "ordertype": "LIMIT", "producttype": product,
            "duration": "DAY", "price": _fmt(price), "quantity": str(qty)}
    if trigger is not None:   # stop-loss orders are their own variety in SmartAPI
        body.update(variety="STOPLOSS", ordertype="STOPLOSS_LIMIT", triggerprice=_fmt(trigger))
    return body


def _gtt(inst: Instrument, qty: int, trigger: Decimal, price: Decimal) -> dict:
    """gttCreateRule body: SELL the delivery holding when LTP reaches `trigger`, as a LIMIT at `price`."""
    return {"tradingsymbol": inst.tradingsymbol, "symboltoken": inst.token, "exchange": EXCHANGE,
            "producttype": SWING_PRODUCT, "transactiontype": "SELL", "price": float(price), "qty": qty,
            "disclosedqty": qty, "triggerprice": float(trigger), "timeperiod": GTT_DAYS}


def _sides(direction: int) -> tuple[str, str]:
    return ("BUY", "SELL") if direction > 0 else ("SELL", "BUY")


def _marketable(ref: float, direction: int, tick: Decimal) -> Decimal:
    """Worst price we accept when crossing the spread: ENTRY_SLIPPAGE beyond `ref`, rounded away from the market."""
    return to_tick(ref * (1 + direction * ENTRY_SLIPPAGE), tick, ROUND_CEILING if direction > 0 else ROUND_FLOOR)


def _entry_limit(ref: float, target: float, direction: int, tick: Decimal) -> Decimal:
    """Marketable entry, but never at or past T1: the backtest doesn't enter a trade that is already done."""
    limit = _marketable(ref, direction, tick)
    if direction > 0:
        return min(limit, to_tick(target, tick, ROUND_CEILING) - tick)
    return max(limit, to_tick(target, tick, ROUND_FLOOR) + tick)


def _skip_reason(ref: float, stop: float, target: float, qty: int, label: str) -> str:
    if qty < 1:
        return "quantity is 0: the stop is too wide for this capital and risk"
    if not min(stop, target) < ref < max(stop, target):
        return f"{label} {ref:,.2f} is at or beyond the stop {stop:,.2f} or T1 {target:,.2f}: the backtest skips it"
    return ""


# ---------- tickets ----------

def swing_ticket(report, inst: Instrument, qty: int, open_price: float) -> Ticket:
    """Swing Buy: place the entry once the session has opened (open_price = today's open), then both GTTs."""
    if report.verdict not in BUY_LEVELS:
        return Ticket(skip=f"verdict is {report.verdict}: only a validated Buy is traded")
    p = report.plan
    if reason := _skip_reason(open_price, p.stop, p.target1, qty, "opened at"):
        return Ticket(skip=reason)
    entry = _order(inst, "BUY", SWING_PRODUCT, qty, _entry_limit(open_price, p.target1, 1, inst.tick))
    exits = (_gtt(inst, qty, to_tick(p.stop, inst.tick), to_tick(p.stop * (1 - STOP_LIMIT_BUFFER), inst.tick, ROUND_FLOOR)),
             _gtt(inst, qty, to_tick(p.target1, inst.tick), to_tick(p.target1, inst.tick, ROUND_FLOOR)))
    return Ticket(entry, exits, f"close of session {MAX_HOLD} (entry day = 1): cancel both GTTs, then exit_now()")


def intraday_ticket(report, inst: Instrument, qty: int, ltp: float) -> Ticket:
    """Intraday setup: entry now; the two exits go in only after the entry is confirmed filled."""
    if report.verdict not in INTRADAY_SETUPS or report.best is None:
        return Ticket(skip=f"verdict is {report.verdict}: only a backtest-supported setup is traded")
    p, direction = report.best.plan, report.best.plan.direction
    if reason := _skip_reason(ltp, p.stop, p.target1, qty, "price"):
        return Ticket(skip=reason)
    entry_side, exit_side = _sides(direction)
    away = ROUND_FLOOR if direction > 0 else ROUND_CEILING      # exit limits rounded so they still fill
    entry = _order(inst, entry_side, INTRADAY_PRODUCT, qty, _entry_limit(ltp, p.target1, direction, inst.tick))
    stop = _order(inst, exit_side, INTRADAY_PRODUCT, qty,
                  to_tick(p.stop * (1 - direction * STOP_LIMIT_BUFFER), inst.tick, away), trigger=to_tick(p.stop, inst.tick))
    target = _order(inst, exit_side, INTRADAY_PRODUCT, qty, to_tick(p.target1, inst.tick, away))
    return Ticket(entry, (stop, target), f"{SQUARE_OFF:%H:%M}: cancel both exits, then exit_now() whatever is still open")


def exit_now(inst: Instrument, product: str, position_qty: int, ltp: float) -> dict:
    """Flatten a position at the time exit: positive qty = long (sell it), negative = short (buy it back)."""
    direction = 1 if position_qty > 0 else -1
    return _order(inst, _sides(direction)[1], product, abs(position_qty), _marketable(ltp, -direction, inst.tick))
