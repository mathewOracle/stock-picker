"""Refresh logic against a throwaway database, with Yahoo mocked out (no network)."""

import pandas as pd
import pytest

from app import data
from tests.conftest import make_ohlcv


@pytest.fixture
def fake_yahoo(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(data, "_fresh_session", lambda: None)
    calls = {"download": 0, "fundamentals": 0}

    def download(symbols, session, **kwargs):
        calls["download"] += 1
        return {s: make_ohlcv([100 + i for i in range(30)]) for s in symbols}

    def fundamentals(symbol, session):
        calls["fundamentals"] += 1
        return {"info": {"sector": "Tech"}, "statements": {}}

    monkeypatch.setattr(data, "_download", download)
    monkeypatch.setattr(data, "_fetch_fundamentals", fundamentals)
    return calls


def test_fundamentals_are_cached_between_refreshes(fake_yahoo):
    first = data.refresh()
    assert first.fundamentals_updated == len(data.STOCKS)
    second = data.refresh()
    assert second.fundamentals_updated == 0               # the optimisation: no refetch within the TTL
    assert fake_yahoo["download"] == 2                     # but prices always refresh
    assert fake_yahoo["fundamentals"] == len(data.STOCKS)


def test_stale_fundamentals_are_refetched(fake_yahoo, monkeypatch):
    data.refresh()
    monkeypatch.setattr(data, "FUNDAMENTALS_TTL", -1)      # everything is now "stale"
    assert data.refresh().fundamentals_updated == len(data.STOCKS)


def test_total_failure_raises_and_keeps_cache(fake_yahoo, monkeypatch):
    data.refresh()
    monkeypatch.setattr(data, "_download", lambda symbols, session, **kw: {})
    with pytest.raises(data.RefreshError):
        data.refresh()
    assert data.load_ohlcv("RELIANCE.NS") is not None      # old data survives


def test_intraday_refresh_does_not_bump_daily_timestamp(fake_yahoo):
    data.refresh()
    daily_stamp = data.last_refresh()
    data.refresh_intraday()
    assert data.last_refresh() == daily_stamp
    assert data.last_intraday_refresh() is not None
    assert isinstance(data.load_intraday("RELIANCE.NS"), pd.DataFrame)


def test_clean_frame_survives_an_empty_yahoo_reply():
    """Yahoo answers a failed ticker with an empty frame on a plain Index: skip it, don't crash the refresh."""
    empty = pd.DataFrame(columns=data.OHLCV)
    assert data._clean_frame(empty).empty


def test_refresh_symbol_touches_only_that_stock(fake_yahoo, monkeypatch):
    data.refresh()
    downloads, original = [], data._download
    monkeypatch.setattr(data, "_download", lambda symbols, session, **kw: (downloads.append(list(symbols)), original(symbols, session, **kw))[1])
    result = data.refresh_symbol("TCS.NS")
    assert downloads == [["TCS.NS", data.BENCHMARK]]            # one stock + Nifty, not 60+ symbols
    assert result.fundamentals_updated == 1 and not result.failed
    assert fake_yahoo["fundamentals"] == len(data.STOCKS) + 1   # statements always re-fetched for a single re-analysis


def test_refresh_symbol_rejects_unknown_and_empty_replies(fake_yahoo, monkeypatch):
    with pytest.raises(ValueError):
        data.refresh_symbol("NOPE.NS")
    data.refresh()
    monkeypatch.setattr(data, "_download", lambda symbols, session, **kw: {})
    with pytest.raises(data.RefreshError, match="TCS.NS"):
        data.refresh_symbol("TCS.NS")
    assert data.load_ohlcv("TCS.NS") is not None                # a failed re-analysis never wipes the cache


def test_per_stock_freshness_is_honest_after_a_single_refresh(fake_yahoo):
    data.refresh()
    stalest_before, last_saved = data.oldest_stock_refresh(), list(data.STOCKS)[-1]   # saved last, so never the oldest
    data.refresh_symbol(last_saved)
    assert data.symbol_fetched_at(last_saved) > stalest_before  # that stock is newer...
    assert data.oldest_stock_refresh() == stalest_before        # ...but 'everything is this fresh' did not move
    assert data.symbol_fetched_at("NOPE.NS") is None


def test_refresh_intraday_can_be_limited_to_some_symbols(fake_yahoo):
    data.refresh_intraday(symbols=["TCS.NS"])
    assert data.load_intraday("TCS.NS") is not None and data.load_intraday("RELIANCE.NS") is None
