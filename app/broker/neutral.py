"""Broker-neutral US order tickets: the fields every US broker needs, until a broker is chosen.

Same plan -> same legs as India (app/broker/tickets.py); only the format and the US specifics differ:

* Rule 612: prices at $1.00 and above in whole cents, below $1 in $0.0001 (app.rules.us.tick_for).
* Exits are ONE OCO order (stop-limit + target limit, one cancels the other), placed after the entry fills, like the
  backtests. Swing uses GTC (a stop must survive overnight; the time exit cancels it), intraday DAY.
* Shorts open with side "sell_short" and close with "buy_to_cover": Reg SHO Rule 200(g) order marking.
* Entries are marketable DAY limits in the REGULAR session only (extended_hours false): the backtests never trade
  pre/post-market bars, and many brokers accept only limit orders there anyway.

Field names are deliberately plain (symbol, side, quantity, order_type, limit_price, stop_price, time_in_force) so
mapping to Alpaca, Schwab or IBKR later is a rename, not a redesign.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.broker.tickets import Legs, Ticket, intraday_gate, legs, marketable, swing_gate
from app.intraday.indicators import SQUARE_OFF
from app.research.backtest import MAX_HOLD
from app.rules.us import tick_for

NAME = "broker-neutral"


@dataclass(frozen=True)
class Instrument:
    symbol: str      # the exchange ticker, e.g. "BRK.B" (Yahoo's BRK-B)
    tick: Decimal


def instrument(symbol: str, ref_price: float) -> tuple[Instrument, bool, str]:
    """(instrument, verified, note). US tickers need no token lookup; Yahoo's class-share dash becomes a dot."""
    return Instrument(symbol.replace("-", "."), tick_for(ref_price)), True, ""


def _price(value: Decimal, tick: Decimal) -> str:
    return str(value.quantize(tick))


def _sides(lg: Legs) -> tuple[str, str]:
    return ("buy", "sell") if lg.direction > 0 else ("sell_short", "buy_to_cover")


def _entry(inst: Instrument, lg: Legs) -> dict:
    return {"symbol": inst.symbol, "side": _sides(lg)[0], "quantity": lg.qty, "order_type": "limit",
            "limit_price": _price(lg.entry, inst.tick), "time_in_force": "day", "extended_hours": False}


def _oco(inst: Instrument, lg: Legs, time_in_force: str) -> dict:
    return {"symbol": inst.symbol, "order_class": "oco", "side": _sides(lg)[1], "quantity": lg.qty,
            "time_in_force": time_in_force,
            "take_profit": {"order_type": "limit", "limit_price": _price(lg.target, inst.tick)},
            "stop_loss": {"order_type": "stop_limit", "stop_price": _price(lg.stop_trigger, inst.tick),
                          "limit_price": _price(lg.stop_limit, inst.tick)}}


def swing_ticket(report, inst: Instrument, qty: int, open_price: float) -> Ticket:
    """Swing Buy: entry after the open (open_price = today's open), then one GTC OCO for the whole quantity."""
    if reason := swing_gate(report, qty, open_price):
        return Ticket(skip=reason)
    lg = legs(report.plan, qty, open_price, inst.tick)
    return Ticket(_entry(inst, lg), (_oco(inst, lg, "gtc"),),
                  f"close of session {MAX_HOLD} (entry day = 1): cancel the OCO, then sell with a marketable limit",
                  legs=lg, product="BUY · limit, day, regular session",
                  exits_note="The exit is one GTC OCO order (stop + target), placed straight after the entry fills.")


def intraday_ticket(report, inst: Instrument, qty: int, ltp: float) -> Ticket:
    """Intraday setup: entry now; one DAY OCO after the fill; flat by the square-off whatever happens."""
    if reason := intraday_gate(report, qty, ltp):
        return Ticket(skip=reason)
    lg = legs(report.best.plan, qty, ltp, inst.tick)
    side = "BUY" if lg.direction > 0 else "SELL SHORT"
    return Ticket(_entry(inst, lg), (_oco(inst, lg, "day"),),
                  f"{SQUARE_OFF:%H:%M} ET: cancel the OCO, then close whatever is still open with exit_now()",
                  legs=lg, product=f"{side} · limit, day, regular session",
                  exits_note="The exit is one DAY OCO order (stop + target), sent only after the entry is confirmed filled.")


def exit_now(inst: Instrument, position_qty: int, ltp: float) -> dict:
    """Flatten at the time exit: positive qty = long (sell it), negative = short (buy to cover)."""
    direction = 1 if position_qty > 0 else -1
    return {"symbol": inst.symbol, "side": "sell" if direction > 0 else "buy_to_cover", "quantity": abs(position_qty),
            "order_type": "limit", "limit_price": _price(marketable(ltp, -direction, inst.tick), inst.tick),
            "time_in_force": "day", "extended_hours": False}
