"""US market rules (app/rules/us.py), each pinned to real NYSE dates. Pure: the calendar is passed in."""

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from app.market.us import MARKET as US
from app.rules import Check, DeskContext, blocking
from app.rules import us as rules

ET = US.clock.tz


def is_session(day: date) -> bool:
    return US.session(day) is not None


def ctx(**overrides) -> DeskContext:
    base = dict(mode="intraday", symbol="AAPL", direction=1, qty=10, ref_price=200.0, account="margin",
                capital=10_000, now=datetime(2026, 11, 25, 10, 30, tzinfo=ET), journal=(), hold_sessions=40)
    return DeskContext(**{**base, **overrides})


def row(day: date, mode="intraday", symbol="MSFT", account="margin", notional=1000.0) -> dict:
    return {"at": datetime(day.year, day.month, day.day, 10, 0, tzinfo=ET).isoformat(), "mode": mode, "symbol": symbol,
            "account": account, "notional": notional}


def statuses(checks: list[Check]) -> dict[str, str]:
    return {c.rule.split(" (")[0]: c.status for c in checks}


# ---------- calendar ----------

def test_t_plus_one_skips_weekends_and_nyse_holidays():
    assert rules.settlement_date(date(2026, 11, 24), is_session) == date(2026, 11, 25)
    assert rules.settlement_date(date(2026, 11, 25), is_session) == date(2026, 11, 27)   # Thanksgiving 26 Nov is shut
    assert rules.settlement_date(date(2026, 11, 27), is_session) == date(2026, 11, 30)   # Friday half-day -> Monday


def test_pdt_window_counts_sessions_not_calendar_days():
    window = rules.recent_sessions(date(2026, 11, 30), 5, is_session)
    assert window == [date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25), date(2026, 11, 27), date(2026, 11, 30)]


# ---------- Rule 612 ----------

@pytest.mark.parametrize("price,tick", [(250.0, "0.01"), (1.00, "0.01"), (0.9999, "0.0001"), (0.35, "0.0001")])
def test_sub_penny_rule(price, tick):
    assert str(rules.tick_for(price)) == tick


# ---------- PDT ----------

def test_pdt_allows_three_day_trades_then_blocks_the_fourth_under_25k():
    today = date(2026, 11, 25)
    two = tuple(row(today - timedelta(days=d)) for d in (1, 2))
    three = (*two, row(today))
    assert rules.pdt_check(ctx(journal=()), is_session).status == "ok"
    assert rules.pdt_check(ctx(journal=two), is_session).status == "warn"       # this one is the 3rd: last allowed
    blocked = rules.pdt_check(ctx(journal=three), is_session)
    assert blocked.status == "block" and "pattern day trader" in blocked.message


def test_pdt_ignores_old_trades_cash_trades_and_swing_orders():
    today = date(2026, 11, 25)
    journal = (row(today - timedelta(days=14)), row(today - timedelta(days=15)), row(today - timedelta(days=16)),
               row(today, account="cash"), row(today, mode="swing"), row(today, mode="swing"))
    assert rules.day_trades(journal, today, is_session) == 0


def test_pdt_does_not_limit_25k_accounts():
    full = tuple(row(date(2026, 11, 25)) for _ in range(6))
    assert rules.pdt_check(ctx(journal=full, capital=25_000), is_session).status == "ok"


def test_legacy_rows_without_account_count_as_margin():
    legacy = {"at": datetime(2026, 11, 25, 10, tzinfo=ET).isoformat(), "mode": "intraday", "symbol": "X"}
    assert rules.day_trades((legacy,), date(2026, 11, 25), is_session) == 1


# ---------- shorting ----------

def test_cash_accounts_cannot_short():
    assert blocking(rules.desk_checks(ctx(direction=-1, account="cash"), is_session)).rule.startswith("Reg T")


def test_rule201_blocks_shorts_and_unknown_status_warns():
    assert blocking(rules.desk_checks(ctx(direction=-1, rule201=True), is_session)).rule.startswith("Reg SHO Rule 201")
    unknown = statuses(rules.desk_checks(ctx(direction=-1, rule201=None), is_session))
    assert unknown["Reg SHO Rule 201"] == "warn" and unknown["Reg SHO Rules 203(b) and 200(g)"] == "warn"
    assert "Reg SHO Rule 201" not in statuses(rules.desk_checks(ctx(direction=1, rule201=True), is_session))


def _bars(closes_by_day: dict[str, list[float]]) -> pd.DataFrame:
    frames = []
    for day, closes in closes_by_day.items():
        idx = pd.date_range(f"{day} 09:30", periods=len(closes), freq="5min", tz=ET)
        frames.append(pd.DataFrame({"Low": closes, "Close": closes}, index=idx))
    return pd.concat(frames)


def test_rule201_triggers_at_ten_percent_and_lasts_into_the_next_session():
    calm = {"2026-11-23": [100, 100], "2026-11-24": [100, 95]}
    assert not rules.rule201_active(_bars(calm))
    crash_today = {"2026-11-23": [100, 100], "2026-11-24": [100, 90]}      # 90 = exactly 10% below 100: triggered
    assert rules.rule201_active(_bars(crash_today))
    next_day = {**crash_today, "2026-11-25": [91, 92]}                      # still restricted the whole next day
    assert rules.rule201_active(_bars(next_day))
    day_after = {**next_day, "2026-11-27": [92, 93]}                        # and lifted the day after that
    assert not rules.rule201_active(_bars(day_after))


def test_rule201_never_looks_ahead():
    bars = _bars({"2026-11-23": [100, 100], "2026-11-24": [100, 99, 89]})
    assert not rules.rule201_active(bars.iloc[:-1]) and rules.rule201_active(bars)


# ---------- cash account / settlement ----------

def test_cash_account_needs_settled_cash_for_every_buy_today():
    today = date(2026, 11, 25)
    spent = (row(today, account="cash", notional=9_500.0),)
    assert rules.desk_checks(ctx(account="cash", journal=()), is_session)[0].status != "block"
    gfv = blocking(rules.desk_checks(ctx(account="cash", journal=spent), is_session))
    assert gfv is not None and "good-faith" in gfv.message


def test_intraday_in_cash_names_the_settlement_day():
    ok = [c for c in rules.desk_checks(ctx(account="cash"), is_session) if c.rule.startswith("Reg T 220.8")][0]
    assert ok.status == "ok" and "Fri 27 Nov" in ok.message   # T+1 from the day before Thanksgiving


# ---------- wash sale, earnings, restricted ----------

def test_wash_sale_warns_inside_thirty_days_only():
    recent = (row(date(2026, 11, 2), symbol="AAPL"),)
    old = (row(date(2026, 10, 20), symbol="AAPL"),)
    assert statuses(rules.desk_checks(ctx(journal=recent), is_session))["IRS section 1091"] == "warn"
    assert "IRS section 1091" not in statuses(rules.desk_checks(ctx(journal=old), is_session))


def test_swing_warns_when_earnings_fall_inside_the_hold():
    inside = statuses(rules.desk_checks(ctx(mode="swing", earnings=date(2026, 12, 20)), is_session))
    outside = statuses(rules.desk_checks(ctx(mode="swing", earnings=date(2027, 4, 1)), is_session))
    assert inside["Earnings inside the hold"] == "warn" and "Earnings inside the hold" not in outside


def test_restricted_list_blocks_whatever_else_is_fine():
    checks = rules.desk_checks(ctx(capital=1e6, restricted=frozenset({"AAPL"})), is_session)
    assert blocking(checks).rule.startswith("Restricted list")


def test_checks_come_worst_first_and_always_include_the_tax_note():
    checks = rules.desk_checks(ctx(direction=-1, rule201=True), is_session)
    order = ["block", "warn", "ok", "info"]
    assert [order.index(c.status) for c in checks] == sorted(order.index(c.status) for c in checks)
    assert any(c.rule.startswith("Holding period") for c in checks)


def test_check_rejects_unknown_status():
    with pytest.raises(ValueError):
        Check("x", "maybe", "y")
