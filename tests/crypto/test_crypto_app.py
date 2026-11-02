"""The engine with the crypto profile ACTIVE. Collected only when STOCK_PICKER_MARKET=crypto (tests/test_crypto_market.py
runs this directory in a subprocess with it set, so a plain `pytest` covers every market). Yahoo is faked: no network.
"""

import zlib

import numpy as np
import pandas as pd
import pytest

from app.market import MARKET

if MARKET.key != "crypto":   # importing the engine binds it to the active market: only ever do that in a crypto process
    pytest.skip("needs STOCK_PICKER_MARKET=crypto", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import data  # noqa: E402
from app.crypto import analysis, coindata  # noqa: E402
from app.crypto.main import app  # noqa: E402
from app.universe import BENCHMARK, STOCKS  # noqa: E402

DAYS = 730
STAIRCASE = "SHIB-USD"     # Yahoo rounds its daily bars to 6 decimals: a handful of distinct closes a year


def _coin_frame(symbol: str) -> pd.DataFrame:
    """Two years of 24/7 daily bars (weekends included); volume is dollars, like Yahoo's crypto volume."""
    rng = np.random.default_rng(zlib.crc32(symbol.encode()))   # hash() is salted per process: not reproducible
    start = 0.0000046 if symbol == STAIRCASE else 50.0
    closes = start * np.cumprod(1 + 0.002 + rng.normal(0, 0.03, DAYS))
    if symbol == STAIRCASE:
        closes = np.maximum(np.round(closes, 6), 1e-6)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame({"Open": opens, "High": np.maximum(opens, closes) * 1.01, "Low": np.minimum(opens, closes) * 0.99,
                         "Close": closes, "Volume": np.full(DAYS, 5e8)},
                        index=pd.date_range("2024-11-03", periods=DAYS, freq="D"))


@pytest.fixture
def fake_yahoo(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(data, "_fresh_session", lambda: None)
    monkeypatch.setattr(analysis, "_memo", None)
    day = {"today": "2026-11-01"}

    def download(symbols, session, **kwargs):
        return {s: _coin_frame(s) for s in symbols}

    def fetch_coin(symbol, session):
        supply = 1e9 * (1.0 if day["today"] == "2026-11-01" else 1.01)
        info = {"marketCap": 2e10, "fullyDilutedValue": 2.2e10, "circulatingSupply": supply, "totalSupply": 1.1e9,
                "maxSupply": 2e9, "averageDailyVolume3Month": 5e8, "allTimeHigh": 200.0, "allTimeLow": 0.0,
                "startDate": 1.4e9}
        return {"info": info, "fetched": day["today"]}

    monkeypatch.setattr(data, "_download", download)
    monkeypatch.setattr(coindata, "fetch_coin", fetch_coin)
    return day


@pytest.fixture
def client(fake_yahoo):
    coindata.refresh()
    return TestClient(app)


# ---------- data ----------

def test_refresh_stores_coins_and_snapshots_their_supply(fake_yahoo, monkeypatch):
    result = coindata.refresh()
    assert result.fundamentals_updated == len(STOCKS) and not result.failed
    assert len(coindata.supply_history()) == len(STOCKS)
    fake_yahoo["today"] = "2026-12-01"
    monkeypatch.setattr(data, "FUNDAMENTALS_TTL", -1)             # a month later the supply has grown 1%
    coindata.refresh()
    assert coindata.supply_history()[BENCHMARK] == {"2026-11-01": 1e9, "2026-12-01": 1.01e9}


def test_tiny_prices_survive_the_cache(fake_yahoo):
    coindata.refresh()
    stored = data.load_ohlcv("DOGE-USD")["Close"]
    assert np.allclose(stored.values, _coin_frame("DOGE-USD")["Close"].values, rtol=1e-5)   # 6 significant figures


# ---------- analysis ----------

def test_every_coin_gets_three_pillars_and_a_verdict(client):
    overview = analysis.build()
    assert len(overview.reports) == len(STOCKS)
    btc = overview.get(BENCHMARK)
    assert [label for label, *_ in btc.pillars] == ["Tokenomics", "Technical", "Chart"] and btc.verdict
    assert overview.regime["label"] and overview.alt_season["alts"] == len(STOCKS) - 1
    assert 0 < overview.dominance < 1 and overview.total_cap == pytest.approx(2e10 * len(STOCKS))


def test_a_staircase_price_feed_can_never_be_a_buy(client):
    shib = analysis.build().get(STAIRCASE)
    assert "Coarse price data" in shib.flags and shib.verdict not in ("Buy", "Strong Buy")
    assert not any("Coarse price data" in r.flags for r in analysis.build().reports if r.symbol != STAIRCASE)


def test_regime_reads_bitcoins_trend_and_volatility():
    assert analysis.crypto_regime({"pct_vs_200dma": -0.1, "off_high": -0.4}, 0.5)["tone"] == "red"
    assert analysis.crypto_regime({"pct_vs_200dma": -0.1, "off_high": -0.1}, 0.5)["tone"] == "amber"
    assert analysis.crypto_regime({"pct_vs_200dma": 0.1, "off_high": -0.1}, 0.9)["label"] == "Uptrend, but violent"
    assert analysis.crypto_regime({"pct_vs_200dma": 0.1, "off_high": -0.1}, 0.4)["tone"] == "green"
    assert analysis.crypto_regime(None, None)["label"] == "Unknown"


def test_weekday_indices_keep_a_252_bar_year():
    assert analysis.bars_per_year(pd.bdate_range("2026-01-01", periods=300)) == 252
    assert analysis.bars_per_year(pd.date_range("2026-01-01", periods=300)) == 365


# ---------- pages ----------

def test_overview_is_the_coin_home_with_crypto_wording(client):
    page = client.get("/").text
    assert "Crypto regime" in page and "Altcoin season index" in page and 'href="/coin/BTC-USD"' in page
    assert "not been backtested" in page and "Order desk" not in page and "Dry run" not in page


def test_coin_page_shows_tokenomics_trade_plan_and_a_precise_chart(client):
    page = client.get("/coin/DOGE-USD").text
    assert "Tokenomics analysis" in page and "Dilution overhang" in page and "Position for 1% risk" in page
    assert "OCO" in page and '"precision": 2' in page
    tiny = client.get(f"/coin/{STAIRCASE}").text
    assert "Price data too coarse to trust" in tiny and '"precision": 2' not in tiny
    assert "All-time low</dt><dd class=\"font-medium\">$–" in tiny     # Yahoo's 0.0 ATL is "unknown", not $0.00


def test_table_filters_by_category(client):
    rows = client.get("/table", params={"category": "Meme"}).text
    assert "Dogecoin" in rows and "Bitcoin</a>" not in rows


def test_unknown_coins_and_stock_links(client):
    assert client.get("/coin/NOPE-USD").status_code == 404
    assert client.get("/market", follow_redirects=False).headers["location"] == "/"
    assert client.get("/stock/BTC-USD", follow_redirects=False).headers["location"] == "/coin/BTC-USD"


def test_single_coin_refresh_needs_the_page_and_a_known_coin(client):
    assert client.post("/coin/BTC-USD/refresh").status_code == 403               # cross-site forms can't set HX-Request
    assert client.post("/coin/NOPE-USD/refresh", headers={"HX-Request": "true"}).status_code == 404
    done = client.post("/coin/BTC-USD/refresh", headers={"HX-Request": "true"})
    assert done.status_code == 200 and done.headers.get("HX-Refresh") == "true"


def test_refresh_job_route_is_shared_with_the_stock_app(client):
    assert client.get("/refresh/daily/status").status_code == 200
    assert client.get("/refresh/research/status").status_code == 404             # no research pipeline for crypto
