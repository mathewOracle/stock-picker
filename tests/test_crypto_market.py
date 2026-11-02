"""Crypto, profile-agnostic: price precision, the crypto profile's facts, tokenomics and the crypto suite in its own process.

Tests that need the crypto engine ACTIVE live in tests/crypto/ and run here in a subprocess with the crypto profile
(the active market is chosen once, at import), so one `pytest` covers India, US and crypto.
"""

import math
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.crypto.tokenomics import HARD_FLAGS, analyze_tokenomics, coin_metrics, supply_growth, tokenomic_flags
from app.market import NAMES, load
from app.market.crypto import COINS, MARKET as CRYPTO
from app.market.india import MARKET as INDIA
from app.market.profile import Market
from app.prices import chart_precision, price_text, round_price
from app.technical import price_metrics, traded_value

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


# ---------- prices: stock output unchanged, coins readable ----------

@pytest.mark.parametrize("value,text", [(2500.46, "2,500.5"), (45.67, "45.7"), (1.25, "1.2"), (0.0752, "0.075"),
                                        (0.00000462, "0.0000046")])
def test_reading_text_keeps_stock_format_and_saves_tiny_prices(value, text):
    assert price_text(value) == text


@pytest.mark.parametrize("value,stored", [(2500.456, 2500.46), (77708.123, 77708.12), (1.253812, 1.25381),
                                          (0.0000046123456, 0.00000461235)])
def test_storage_keeps_six_significant_figures_and_at_least_two_decimals(value, stored):
    assert round_price(value) == pytest.approx(stored, rel=1e-9)


def test_chart_axis_gets_enough_decimals():
    assert [chart_precision(p) for p in (2500.0, 45.0, 1.25, 0.075, 0.0000046)] == [2, 2, 3, 5, 9]   # 4 significant figures


def test_non_finite_prices_do_not_crash_formatting():
    assert round_price(0.0) == 0.0 and math.isnan(round_price(float("nan")))


# ---------- the crypto profile ----------

def test_crypto_is_a_selectable_market_with_its_own_home():
    assert "crypto" in NAMES and load("crypto") is CRYPTO and load("CRYPTO").key == "crypto"
    assert CRYPTO.data_dir.name == "data-crypto" and CRYPTO.default_port not in (INDIA.default_port, load("us").default_port)
    assert CRYPTO.worker == "app.crypto.main:app" and INDIA.worker == "app.main:app"


def test_crypto_trades_every_day_of_the_year():
    assert all(CRYPTO.session(date(2026, 12, d)) is not None for d in range(19, 32))   # weekends + Christmas
    assert CRYPTO.spans.year == 365 and CRYPTO.spans.month == 30 and CRYPTO.spans.quarter == 91
    assert INDIA.spans.year == 252 and INDIA.spans.month == 21                       # stocks unchanged


def test_crypto_volume_is_already_dollars():
    frame = pd.DataFrame({"Close": [0.5] * 30, "Volume": [2e8] * 30})   # Yahoo crypto volume = $200M a day
    assert traded_value(frame, market=CRYPTO) == pytest.approx(200)                 # millions, not 0.5 x 200M coins
    assert traded_value(frame, market=INDIA) == pytest.approx(0.5 * 2e8 / 1e7)      # stocks: close x shares


def test_returns_use_the_markets_own_calendar():
    close = pd.Series(range(1, 400), dtype=float)
    assert price_metrics(close, year=365)["ret_1m"] == pytest.approx(close.iloc[-1] / close.iloc[-31] - 1)
    assert price_metrics(close)["ret_1m"] == pytest.approx(close.iloc[-1] / close.iloc[-22] - 1)


def test_coin_tickers_display_without_yahoos_ids():
    assert [CRYPTO.short_symbol(s) for s in ("BTC-USD", "SUI20947-USD", "PEPE24478-USD")] == ["BTC", "SUI", "PEPE"]
    assert CRYPTO.category("DOGE-USD") == "Meme" and CRYPTO.category("NOPE") == "Other"


def test_universe_has_no_stablecoins_and_bitcoin_is_the_benchmark():
    assert CRYPTO.benchmark == "BTC-USD" and CRYPTO.benchmark in CRYPTO.stocks
    assert not {"USDT-USD", "USDC-USD", "DAI-USD"} & set(COINS) and len(COINS) >= 30
    assert CRYPTO.money.big(2.19e12) == "$2.19T"


# ---------- tokenomics ----------

def _info(**overrides) -> dict:
    base = {"marketCap": 1.5e12, "fullyDilutedValue": 1.6e12, "circulatingSupply": 19.9e6, "totalSupply": 19.9e6,
            "maxSupply": 21e6, "averageDailyVolume3Month": 3e10, "allTimeHigh": 126000, "allTimeLow": 0.05,
            "startDate": datetime(2010, 7, 13, tzinfo=timezone.utc).timestamp()}
    return {**base, **overrides}


def test_a_bitcoin_like_coin_scores_well_on_tokenomics():
    m = coin_metrics(_info(), 77700, now=NOW)
    assert m["fdv_ratio"] == pytest.approx(1.6 / 1.5) and m["has_cap"] and m["age_years"] > 16
    assert m["off_ath"] == pytest.approx(77700 / 126000 - 1) and m["turnover"] == pytest.approx(0.02)
    signals = {s.name: s for s in analyze_tokenomics(m, "Store of value")}
    assert signals["Network size (market cap)"].points == 1 and signals["Supply cap"].points > 0
    assert tokenomic_flags(m, "Store of value") == []


def test_a_locked_up_young_illiquid_token_is_vetoed():
    info = _info(marketCap=5e8, fullyDilutedValue=4e9, maxSupply=None, averageDailyVolume3Month=1e6,
                 startDate=datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp())
    m = coin_metrics(info, 1.0, now=NOW)
    flags = tokenomic_flags(m, "DeFi")
    assert {"Heavy dilution", "Illiquid", "Young coin (< 2 yrs)"} <= set(flags)
    assert {"Heavy dilution", "Illiquid"} <= HARD_FLAGS
    dilution = next(s for s in analyze_tokenomics(m, "DeFi") if s.name.startswith("Dilution"))
    assert dilution.points == -1


def test_missing_coin_data_is_unknown_not_a_guess():
    m = coin_metrics({"allTimeLow": 0.0}, 0.0000046, now=NOW)   # Yahoo really does report SHIB's ATL as 0.0
    assert all(math.isnan(m[k]) for k in ("market_cap", "fdv_ratio", "turnover", "atl", "x_from_atl", "age_years"))
    assert analyze_tokenomics(m, "Payments") == [] or all(s.weight == 0 for s in analyze_tokenomics(m, "Payments"))


def test_meme_coins_carry_a_utility_penalty_and_a_flag():
    m = coin_metrics(_info(), 77700, now=NOW)
    assert any(s.name == "Utility claim" and s.points < 0 for s in analyze_tokenomics(m, "Meme"))
    assert "Meme coin" in tokenomic_flags(m, "Meme")


def test_supply_inflation_needs_a_month_of_snapshots():
    assert supply_growth({"2026-10-20": 100, "2026-11-01": 101}) == (pytest.approx(float("nan"), nan_ok=True), 12)
    rate, days = supply_growth({"2025-11-01": 100, "2026-05-02": 101, "2026-11-01": 102})
    assert days == 365 and rate == pytest.approx(0.02)
    m = coin_metrics(_info(), 77700, {"2025-11-01": 100, "2026-11-01": 102}, now=NOW)
    inflation = next(s for s in analyze_tokenomics(m, "Store of value") if s.name.startswith("Supply inflation"))
    assert inflation.weight > 0 and inflation.points == 0.3     # 2% a year: modest issuance


def test_collecting_supply_history_is_shown_but_not_scored():
    m = coin_metrics(_info(), 77700, now=NOW)
    inflation = next(s for s in analyze_tokenomics(m, "Store of value") if s.name.startswith("Supply inflation"))
    assert inflation.weight == 0 and "collecting" in inflation.reading


def test_profiles_default_to_stock_behaviour():
    assert Market.__dataclass_fields__["trading_days"].default == 252
    assert Market.__dataclass_fields__["volume_in_money"].default is False


# ---------- the crypto engine, active ----------

@pytest.mark.skipif(os.environ.get("STOCK_PICKER_MARKET", "india").lower() == "crypto", reason="already running as crypto")
def test_the_crypto_suite_passes_with_the_crypto_profile_active():
    env = {**os.environ, "STOCK_PICKER_MARKET": "crypto"}
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/crypto"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-2000:]
