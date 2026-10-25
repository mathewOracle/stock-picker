"""Angel One order bodies: every parameter pinned, plus the rules that decide whether an order exists at all."""

import json
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from types import SimpleNamespace

import pytest

from app.broker.angelone import (GTT_DAYS, Instrument, exit_now, instrument, intraday_ticket, position_size,
                                 swing_ticket, to_tick)
from app.research.backtest import MAX_HOLD
from app.tradeplan import TradePlan

MASTER = [   # the same name on three segments: only the NSE cash row is the right one
    {"token": "2885", "symbol": "RELIANCE-EQ", "exch_seg": "NSE", "tick_size": "5.000000"},
    {"token": "500325", "symbol": "RELIANCE-EQ", "exch_seg": "BSE", "tick_size": "5.000000"},
    {"token": "99999", "symbol": "RELIANCE", "exch_seg": "NFO", "tick_size": "10.000000"},
    {"token": "1111", "symbol": "PENNY-EQ", "exch_seg": "NSE", "tick_size": "1.000000"},
]
INST = Instrument("RELIANCE-EQ", "2885", Decimal("0.05"))
SWING_PLAN = TradePlan(2000, 1900, 2200, 2300, "test")


def _swing(verdict="Buy", plan=SWING_PLAN):
    return SimpleNamespace(verdict=verdict, plan=plan)


def _intraday(plan, verdict=None):
    side = "Long" if plan.direction > 0 else "Short"
    return SimpleNamespace(verdict=verdict or f"{side} setup", best=SimpleNamespace(plan=plan, side=side))


def test_instrument_takes_only_the_nse_cash_row_and_converts_paise_ticks():
    assert instrument(MASTER, "RELIANCE.NS") == INST
    assert instrument(MASTER, "PENNY.NS").tick == Decimal("0.01")
    with pytest.raises(LookupError):
        instrument(MASTER, "NOPE.NS")
    with pytest.raises(LookupError):   # two NSE rows = ambiguous: refuse rather than guess
        instrument([*MASTER, MASTER[0]], "RELIANCE.NS")


def test_prices_snap_to_the_tick_grid_in_the_requested_direction():
    tick = Decimal("0.05")
    assert to_tick(1845.03, tick) == Decimal("1845.05")
    assert to_tick(1845.03, tick, ROUND_FLOOR) == Decimal("1845.00")
    assert to_tick(1845.01, tick, ROUND_CEILING) == Decimal("1845.05")


@pytest.mark.parametrize("args,qty", [   # the cases in tests/js/position-size.test.js: Python and JS must agree
    ((100000, 1, 100, 80), 50), ((100000, 2, 100, 80), 100), ((100000, 1, 10287, 10267), 9),
    ((100000, 1, 100, 110), 100), ((100000, 1, 100, 100), 0), ((100000, 1, 2000, 1900), 10),
])
def test_position_size_matches_the_javascript_sizer(args, qty):
    assert position_size(*args) == qty


def test_swing_ticket_trades_the_plan_like_the_backtest():
    t = swing_ticket(_swing(), INST, 10, open_price=2010)
    assert t.entry == {"variety": "NORMAL", "tradingsymbol": "RELIANCE-EQ", "symboltoken": "2885",
                       "transactiontype": "BUY", "exchange": "NSE", "ordertype": "LIMIT", "producttype": "DELIVERY",
                       "duration": "DAY", "price": "2020.05", "quantity": "10"}       # 0.5% marketable limit
    stop, target = t.exits
    common = {"tradingsymbol": "RELIANCE-EQ", "symboltoken": "2885", "exchange": "NSE", "producttype": "DELIVERY",
              "transactiontype": "SELL", "qty": 10, "disclosedqty": 10, "timeperiod": GTT_DAYS}
    assert stop == {**common, "triggerprice": 1900.0, "price": 1862.0}    # limit 2% under the trigger: fills in a fall
    assert target == {**common, "triggerprice": 2200.0, "price": 2200.0}  # whole quantity at T1, T2 is never an order
    assert GTT_DAYS > MAX_HOLD * 7 / 5 and f"session {MAX_HOLD}" in t.time_exit   # GTTs outlive the time exit


@pytest.mark.parametrize("verdict,open_price,qty,why", [
    ("Watchlist", 2010, 10, "only a validated Buy"),
    ("Hold", 2010, 10, "only a validated Buy"),
    ("Buy", 1900, 10, "at or beyond"),       # opened on the stop
    ("Buy", 1850, 10, "at or beyond"),       # gapped below it
    ("Buy", 2200, 10, "at or beyond"),       # opened on T1: trade already done
    ("Buy", 2010, 0, "quantity is 0"),
])
def test_swing_ticket_refuses_what_the_backtest_would_not_trade(verdict, open_price, qty, why):
    t = swing_ticket(_swing(verdict), INST, qty, open_price)
    assert t.entry is None and t.exits == () and why in t.skip


def test_entry_limit_never_reaches_t1():
    assert swing_ticket(_swing(), INST, 10, open_price=2195).entry["price"] == "2199.95"   # not 2206.00


def test_intraday_long_ticket():
    t = intraday_ticket(_intraday(TradePlan(100, 98, 104, 106, "x")), INST, 50, ltp=100.2)
    assert (t.entry["transactiontype"], t.entry["producttype"], t.entry["price"]) == ("BUY", "INTRADAY", "100.75")
    stop, target = t.exits
    assert (stop["variety"], stop["ordertype"], stop["transactiontype"]) == ("STOPLOSS", "STOPLOSS_LIMIT", "SELL")
    assert (stop["triggerprice"], stop["price"], stop["producttype"]) == ("98.00", "96.00", "INTRADAY")
    assert (target["variety"], target["ordertype"], target["transactiontype"], target["price"]) == \
        ("NORMAL", "LIMIT", "SELL", "104.00")
    assert "triggerprice" not in target and "15:15" in t.time_exit


def test_intraday_short_ticket_mirrors_every_side_and_rounding():
    t = intraday_ticket(_intraday(TradePlan(100, 102, 96, 94, "x")), INST, 50, ltp=99.9)
    stop, target = t.exits
    assert (t.entry["transactiontype"], t.entry["price"]) == ("SELL", "99.40")
    assert (stop["transactiontype"], stop["triggerprice"], stop["price"]) == ("BUY", "102.00", "104.05")
    assert (target["transactiontype"], target["price"]) == ("BUY", "96.00")


@pytest.mark.parametrize("verdict,ltp,why", [
    ("Long candidate", 100.2, "only a backtest-supported setup"),   # rules fired, backtest didn't back it
    ("No trade", 100.2, "only a backtest-supported setup"),         # e.g. after 14:45
    (None, 104.0, "at or beyond"),                                  # price already at T1
    (None, 97.9, "at or beyond"),                                   # price already through the stop
])
def test_intraday_ticket_refusals(verdict, ltp, why):
    t = intraday_ticket(_intraday(TradePlan(100, 98, 104, 106, "x"), verdict), INST, 50, ltp)
    assert t.entry is None and why in t.skip


def test_exit_now_flattens_either_side_with_a_marketable_limit():
    sell = exit_now(INST, "DELIVERY", 10, ltp=2100)
    assert (sell["transactiontype"], sell["price"], sell["quantity"]) == ("SELL", "2089.50", "10")
    cover = exit_now(INST, "INTRADAY", -5, ltp=100)
    assert (cover["transactiontype"], cover["price"], cover["quantity"]) == ("BUY", "100.50", "5")


def test_every_body_is_json_ready_and_on_the_tick_grid():
    """The SDK json.dumps() the body: a stray Decimal would crash, an off-grid price would be rejected."""
    bodies = [*swing_ticket(_swing(), INST, 10, 2010).exits, swing_ticket(_swing(), INST, 10, 2010).entry,
              *intraday_ticket(_intraday(TradePlan(100.13, 98.07, 104.11, 106, "x")), INST, 7, 100.33).exits]
    json.dumps(bodies)
    for body in bodies:
        for key in ("price", "triggerprice"):
            if key in body:
                assert Decimal(str(body[key])) % INST.tick == 0, body
