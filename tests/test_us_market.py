"""Market profiles: the US profile's facts, India's unchanged ones, and the US-mode suite run in its own process.

The active market is chosen once, at import (STOCK_PICKER_MARKET). Tests that need the US engine ACTIVE live in
tests/us/ and run here in a subprocess with the US profile, so one `pytest` checks both markets honestly.
"""

import os
import subprocess
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.market import load
from app.market.india import MARKET as INDIA
from app.market.profile import shift
from app.market.us import MARKET as US

ROOT = Path(__file__).resolve().parents[1]
UTC = ZoneInfo("UTC")


# ---------- selection and isolation ----------

def test_market_is_chosen_by_environment_and_defaults_to_india():
    assert load(None).key == "india" and load("us").key == "us" and load("US").key == "us"
    with pytest.raises(ValueError):
        load("japan")


def test_each_market_has_its_own_data_docs_and_port():
    assert INDIA.data_dir != US.data_dir and INDIA.docs_dir != US.docs_dir and INDIA.default_port != US.default_port
    assert US.data_dir.name == "data-us" and US.docs_dir == ROOT / "docs" / "us"


# ---------- US calendar (NYSE via exchange_calendars) ----------

@pytest.mark.parametrize("day", ["2026-04-03", "2026-06-19", "2026-07-03", "2026-11-26", "2026-12-25", "2027-01-01"])
def test_nyse_holidays_are_closed(day):   # Good Friday, Juneteenth, July 4th observed, Thanksgiving, Christmas, New Year
    assert US.session(date.fromisoformat(day)) is None


@pytest.mark.parametrize("day", ["2026-11-27", "2026-12-24"])
def test_nyse_half_days_close_at_one(day):
    assert US.session(date.fromisoformat(day)).close == time(13, 0)


def test_weekends_closed_and_normal_days_full():
    assert US.session(date(2026, 10, 31)) is None
    assert US.session(date(2026, 10, 27)).close == time(16, 0) and US.knows_holidays


@pytest.mark.parametrize("day,utc_hour", [("2026-03-06", 14), ("2026-03-09", 13), ("2026-10-30", 13), ("2026-11-02", 14)])
def test_the_open_follows_new_york_daylight_saving(day, utc_hour):
    """09:30 New York is 13:30 UTC in summer and 14:30 UTC in winter: never a fixed UTC offset."""
    opened = datetime.combine(date.fromisoformat(day), US.clock.open, tzinfo=US.clock.tz).astimezone(UTC)
    assert (opened.hour, opened.minute) == (utc_hour, 30)


def test_us_clock_derives_every_intraday_time_from_open_and_close():
    c = US.clock
    assert (c.open, c.close, c.early_start) == (time(9, 30), time(16, 0), time(4, 0))
    assert shift(c.open, c.opening_range_minutes) == time(9, 45)
    assert shift(c.close, -c.last_entry_before_close) == time(15, 15)
    assert shift(c.close, -c.square_off_before_close) == time(15, 45)


# ---------- India is unchanged ----------

def test_india_profile_reproduces_the_original_constants():
    c = INDIA.clock
    assert c.tz.key == "Asia/Kolkata" and (c.open, c.close) == (time(9, 15), time(15, 30))
    assert shift(c.open, c.opening_range_minutes) == time(9, 30)
    assert shift(c.close, -c.last_entry_before_close) == time(14, 45)
    assert shift(c.close, -c.square_off_before_close) == time(15, 15)
    assert (INDIA.swing_cost_per_side, INDIA.intraday_cost_per_side, INDIA.benchmark) == (0.0015, 0.0006, "^NSEI")
    assert INDIA.money.big(1.5e11) == "₹15,000 Cr" and INDIA.money.big_units(100) == "₹100 Cr"


# ---------- US money, symbols, universe ----------

def test_us_money_reads_like_a_us_finance_page():
    assert [US.money.big(v) for v in (3.9e12, 452.3e9, 25e6)] == ["$3.90T", "$452B", "$25.0M"]
    assert US.money.big_units(1830) == "$1.83B"     # traded value is stored in millions


def test_us_universe_is_us_tickers_with_an_independent_u2():
    assert US.benchmark == "^GSPC" and US.vix == "^VIX" and US.benchmark not in US.stocks
    assert not any(s.endswith(".NS") for s in US.stocks)
    assert len(US.stocks) >= 60 and len(set(US.u2_candidates) - set(US.stocks)) >= 150
    assert US.short_symbol("AAPL") == "AAPL" and INDIA.short_symbol("RELIANCE.NS") == "RELIANCE"


# ---------- the US engine, active ----------

@pytest.mark.skipif(os.environ.get("STOCK_PICKER_MARKET", "india").lower() == "us", reason="already running as US")
def test_the_us_suite_passes_with_the_us_profile_active():
    env = {**os.environ, "STOCK_PICKER_MARKET": "us"}
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/us"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-2000:]
