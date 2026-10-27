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
from decimal import Decimal

from app.broker.tickets import (ENTRY_SLIPPAGE, INTRADAY_SETUPS, STOP_LIMIT_BUFFER, Ticket, intraday_gate, legs,
                                marketable, position_size, swing_gate, to_tick)
from app.intraday.indicators import SQUARE_OFF
from app.research.backtest import MAX_HOLD

__all__ = ["ENTRY_SLIPPAGE", "INTRADAY_SETUPS", "STOP_LIMIT_BUFFER", "GTT_DAYS", "Instrument", "Ticket", "exit_now",
           "instrument", "intraday_ticket", "position_size", "swing_ticket", "to_tick"]

EXCHANGE = "NSE"
SWING_PRODUCT, INTRADAY_PRODUCT = "DELIVERY", "INTRADAY"   # Angel One's names for CNC and MIS
GTT_DAYS = 2 * MAX_HOLD   # 40 sessions ~ 58 calendar days; doubled so holidays never expire a GTT before the time exit
_PAISE = Decimal("0.01")


@dataclass(frozen=True)
class Instrument:
    tradingsymbol: str    # "RELIANCE-EQ"
    token: str            # Angel One symboltoken
    tick: Decimal         # price step in rupees


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


# ---------- tickets ----------

def swing_ticket(report, inst: Instrument, qty: int, open_price: float) -> Ticket:
    """Swing Buy: place the entry once the session has opened (open_price = today's open), then both GTTs."""
    if reason := swing_gate(report, qty, open_price):
        return Ticket(skip=reason)
    lg = legs(report.plan, qty, open_price, inst.tick)
    entry = _order(inst, "BUY", SWING_PRODUCT, qty, lg.entry)
    exits = (_gtt(inst, qty, lg.stop_trigger, lg.stop_limit), _gtt(inst, qty, lg.target_trigger, lg.target))
    return Ticket(entry, exits, f"close of session {MAX_HOLD} (entry day = 1): cancel both GTTs, then exit_now()",
                  legs=lg, product=f"{SWING_PRODUCT} · LIMIT (day)",
                  exits_note="The two exits are GTT rules, created straight after the entry fills.")


def intraday_ticket(report, inst: Instrument, qty: int, ltp: float) -> Ticket:
    """Intraday setup: entry now; the two exits go in only after the entry is confirmed filled."""
    if reason := intraday_gate(report, qty, ltp):
        return Ticket(skip=reason)
    lg = legs(report.best.plan, qty, ltp, inst.tick)
    entry = _order(inst, lg.side, INTRADAY_PRODUCT, qty, lg.entry)
    stop = _order(inst, lg.exit_side, INTRADAY_PRODUCT, qty, lg.stop_limit, trigger=lg.stop_trigger)
    target = _order(inst, lg.exit_side, INTRADAY_PRODUCT, qty, lg.target)
    return Ticket(entry, (stop, target), f"{SQUARE_OFF:%H:%M}: cancel both exits, then exit_now() whatever is still open",
                  legs=lg, product=f"{INTRADAY_PRODUCT} · LIMIT (day)",
                  exits_note="The two exits are orders, sent only after the entry is confirmed filled.")


def exit_now(inst: Instrument, product: str, position_qty: int, ltp: float) -> dict:
    """Flatten a position at the time exit: positive qty = long (sell it), negative = short (buy it back)."""
    direction = 1 if position_qty > 0 else -1
    side = "SELL" if direction > 0 else "BUY"
    return _order(inst, side, product, abs(position_qty), marketable(ltp, -direction, inst.tick))
