"""The engine with the US profile ACTIVE. Collected only when STOCK_PICKER_MARKET=us (tests/test_us_market.py runs
this directory in a subprocess with it set, so a plain `pytest` covers both markets)."""

import json
from datetime import date, datetime, time
from types import SimpleNamespace

import pandas as pd
import pytest

from app.market import MARKET

if MARKET.key != "us":   # importing the engine binds it to the active market: only ever do that in a US process
    pytest.skip("needs STOCK_PICKER_MARKET=us", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import data  # noqa: E402
from app.broker import desk, neutral  # noqa: E402
from app.intraday import analysis as intraday  # noqa: E402
from app.intraday.indicators import NO_NEW_ENTRIES, OPENING_RANGE_END, SQUARE_OFF  # noqa: E402
from app.intraday.setups import PLAYBOOKS, Setup  # noqa: E402
from app.main import app  # noqa: E402
from app.rules import intraday_block  # noqa: E402
from app.tradeplan import TradePlan  # noqa: E402
from app.universe import BENCHMARK, STOCKS  # noqa: E402

ET = MARKET.clock.tz
NOW = datetime(2026, 11, 24, 10, 30, tzinfo=ET)   # an ordinary Tuesday session


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "BROKER_DIR", tmp_path)
    monkeypatch.setattr(desk, "JOURNAL", tmp_path / "orders.jsonl")
    monkeypatch.setattr(desk, "RESTRICTED", tmp_path / "restricted.txt")


# ---------- the engine is bound to the US profile ----------

def test_engine_constants_come_from_the_us_profile():
    assert (OPENING_RANGE_END, NO_NEW_ENTRIES, SQUARE_OFF) == (time(9, 45), time(15, 15), time(15, 45))
    assert BENCHMARK == "^GSPC" and "AAPL" in STOCKS and data.DB_PATH.parent.name == "data-us"
    assert desk.BROKER is neutral and desk.ACCOUNTS == ("margin", "cash")


@pytest.mark.parametrize("now,phase,accepting", [
    (datetime(2026, 11, 26, 11, 0), "Closed (holiday)", False),                      # Thanksgiving
    (datetime(2026, 11, 27, 12, 0), "Open: trading window", True),                   # half-day, before its cutoff
    (datetime(2026, 11, 27, 12, 20), "Open: no new entries (square-off time)", False),  # 12:15 = 13:00 - 45 min
    (datetime(2026, 11, 27, 13, 5), "Closed", False),                                # the half-day is over
    (datetime(2026, 11, 24, 1, 45), "Closed (overnight)", False),
    (datetime(2026, 11, 24, 7, 0), "Pre-market (extended hours)", False),
    (datetime(2026, 11, 24, 9, 40), "Opening range forming", False),
    (datetime(2026, 11, 24, 15, 20), "Open: no new entries (square-off time)", False),
])
def test_market_phase_knows_nyse_holidays_and_half_days(now, phase, accepting):
    label, _, ok = intraday.market_phase(now.replace(tzinfo=ET))
    assert (label, ok) == (phase, accepting)


def test_entry_cutoff_follows_each_days_own_close():
    assert intraday.entry_cutoff(date(2026, 11, 24)) == time(15, 15)
    assert intraday.entry_cutoff(date(2026, 12, 24)) == time(12, 15)


# ---------- Rule 201 is enforced by the live verdict (the backtest calls the same intraday_block) ----------

def _crash_bars() -> pd.DataFrame:
    days = {"2026-11-20": [100.0] * 78, "2026-11-23": [100.0] * 40 + [89.0] * 38, "2026-11-24": [90.0] * 12}
    frames = [pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6},
                           index=pd.date_range(f"{d} 09:30", periods=len(c), freq="5min")) for d, c in days.items()]
    return pd.concat(frames)


def test_rule201_blocks_short_setups_but_not_longs():
    bars = _crash_bars()
    assert "Rule 201" in intraday_block(bars, "Short") and intraday_block(bars, "Long") == ""


def test_decide_refuses_a_short_while_rule201_is_active():
    short = Setup(PLAYBOOKS["orb"], "Short", "t", TradePlan(90, 92, 86, 84, "x"))
    report = SimpleNamespace(issues=[], setups=[short], scores={"bias": 10}, snapshot=SimpleNamespace(bars=_crash_bars()))
    status = SimpleNamespace(is_open=True, phase="Open: trading window")
    verdict, reason, best = intraday.decide(report, status, {})
    assert verdict == "No trade" and "Rule 201" in reason and best is None


# ---------- the order desk: broker-neutral tickets + US rules ----------

BUY = SimpleNamespace(verdict="Buy", plan=TradePlan(200.0, 190.0, 220.0, 230.0, "test"), blockers=[], metrics={})


def _intraday(side: str):
    plan = TradePlan(200.0, 198.0, 204.0, 206.0, "t") if side == "Long" else TradePlan(200.0, 202.0, 196.0, 194.0, "t")
    snap = SimpleNamespace(bars=_crash_bars().iloc[:78 + 40], price=200.0, day=None)   # no crash yet: Rule 201 inactive
    return SimpleNamespace(verdict=f"{side} setup", best=SimpleNamespace(plan=plan, side=side), snapshot=snap)


def test_swing_buy_is_a_cent_priced_limit_with_one_gtc_oco_exit():
    d = desk.build_draft("swing", "AAPL", BUY, (201.0, "open"), 100_000, 1, account="margin", now=NOW)
    assert d.can_place and d.qty == 90   # $1,000 risk / (201 open - 190 stop)
    assert d.ticket.entry == {"symbol": "AAPL", "side": "buy", "quantity": 90, "order_type": "limit",
                              "limit_price": "202.01", "time_in_force": "day", "extended_hours": False}
    (oco,) = d.ticket.exits
    assert oco["order_class"] == "oco" and oco["time_in_force"] == "gtc" and oco["side"] == "sell"
    assert oco["stop_loss"] == {"order_type": "stop_limit", "stop_price": "190.00", "limit_price": "186.20"}
    assert oco["take_profit"] == {"order_type": "limit", "limit_price": "220.00"}
    assert any(c.rule.startswith("SEC Rule 15c6-1") and "Wed 25 Nov" in c.message for c in d.checks)


def test_class_shares_use_the_exchange_ticker_and_penny_stocks_subpenny_ticks():
    inst, verified, _ = neutral.instrument("BRK-B", 480.0)
    assert inst.symbol == "BRK.B" and str(inst.tick) == "0.01" and verified
    assert str(neutral.instrument("XYZ", 0.42)[0].tick) == "0.0001"


def test_intraday_short_is_marked_sell_short_and_closes_with_buy_to_cover():
    d = desk.build_draft("intraday", "AAPL", _intraday("Short"), (200.0, "bar"), 100_000, 1, account="margin", now=NOW)
    assert d.ticket.entry["side"] == "sell_short" and d.ticket.exits[0]["side"] == "buy_to_cover"
    assert d.ticket.exits[0]["time_in_force"] == "day"
    rules = {c.rule.split(" (")[0]: c.status for c in d.checks}
    assert rules["Reg SHO Rules 203(b) and 200(g)"] == "warn" and "Reg SHO Rule 201" not in rules
    assert d.can_place   # $100k equity: PDT does not apply; no circuit breaker yet


def test_cash_account_cannot_short_and_the_server_refuses_to_record_it():
    d = desk.build_draft("intraday", "AAPL", _intraday("Short"), (200.0, "bar"), 100_000, 1, account="cash", now=NOW)
    assert not d.can_place and "margin account" in d.why_not
    with pytest.raises(desk.OrderRefused, match="margin account"):
        desk.record(d, NOW)


def test_fourth_day_trade_under_25k_is_refused_from_the_journal():
    for day in (19, 20, 23):   # three intraday orders in the last five sessions
        rows = [json.dumps({"id": day, "at": datetime(2026, 11, day, 10, tzinfo=ET).isoformat(), "mode": "intraday",
                            "symbol": f"S{day}", "account": "margin", "notional": 1000})]
        with desk.JOURNAL.open("a") as fh:
            fh.write("\n".join(rows) + "\n")
    d = desk.build_draft("intraday", "AAPL", _intraday("Long"), (200.0, "bar"), 20_000, 1, account="margin", now=NOW)
    assert not d.can_place and "pattern day trader" in d.why_not


def test_recorded_rows_carry_account_and_notional_for_later_rules():
    d = desk.build_draft("swing", "AAPL", BUY, (201.0, "open"), 100_000, 1, account="cash", now=NOW)
    row = desk.record(d, NOW)
    assert row["account"] == "cash" and row["notional"] == pytest.approx(90 * 201.0)
    assert all(set(c) == {"rule", "status"} for c in row["checks"])


def test_restricted_list_blocks_the_symbol():
    desk.RESTRICTED.write_text("# employer pre-clearance\nAAPL\n")
    d = desk.build_draft("swing", "AAPL", BUY, (201.0, "open"), 100_000, 1, account="margin", now=NOW)
    assert not d.can_place and "restricted list" in d.why_not


# ---------- the pages speak US ----------

INDIA_WORDS = ("Nifty", "NSE", "Rs ", " IST", "₹", "Angel One", "SEBI", " Cr<", " Cr ", ".NS")


@pytest.mark.parametrize("path", ["/", "/?tab=intraday", "/research/swing", "/research/intraday"])
def test_pages_render_without_india_terms(path):
    page = TestClient(app).get(path)
    assert page.status_code == 200
    leaks = [w for w in INDIA_WORDS if w in page.text]
    assert not leaks, f"India terms on {path}: {leaks}"
    assert "Stock Picker" in page.text or path.startswith("/research")
