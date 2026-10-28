"""Market overview data: index cards, chart series and market internals (fake data, so any market profile works)."""

from types import SimpleNamespace as NS

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import data, marketview
from app.main import app
from app.universe import BENCHMARK, INDICES, VIX


def stock(sector, ret_1d, ret_1m=0.0):
    return NS(metrics={"sector": sector, "ret_1d": ret_1d, "ret_1m": ret_1m})


def test_kind_separates_comparable_indices_from_volatility_and_currency():
    assert marketview.kind(BENCHMARK) == "index"
    assert marketview.kind(VIX) == "vol"
    assert marketview.kind("INR=X") == "fx"


def test_cards_put_indices_first_then_volatility_then_currency_keeping_profile_order():
    cards = marketview.cards([{"symbol": "INR=X"}, {"symbol": VIX}, {"symbol": "^B"}, {"symbol": "^A"}])
    assert [(c["symbol"], c["kind"]) for c in cards] == [("^B", "index"), ("^A", "index"), (VIX, "vol"), ("INR=X", "fx")]


def test_internals_count_advancers_and_decliners_and_ignore_missing_returns():
    net = marketview.internals([stock("Tech", 0.02), stock("Tech", -0.01), stock("Bank", 0.0), stock("Bank", float("nan"))], 0.65)
    assert (net["advancers"], net["decliners"], net["unchanged"], net["tracked"]) == (1, 1, 1, 3)
    assert net["breadth"] == 0.65


def test_sectors_are_averaged_sorted_best_first_and_barred_against_the_biggest_move():
    net = marketview.internals([stock("Tech", 0.04, 0.10), stock("Tech", 0.02, 0.06), stock("Bank", -0.01, 0.02),
                                stock("Energy", 0.0, float("nan"))], None)
    rows = {r["name"]: r for r in net["sectors"]}
    assert [r["name"] for r in net["sectors"]] == ["Tech", "Energy", "Bank"]
    assert rows["Tech"]["ret_1d"] == pytest.approx(0.03) and rows["Tech"]["ret_1m"] == pytest.approx(0.08) and rows["Tech"]["n"] == 2
    assert rows["Tech"]["bar"] == 100 and rows["Bank"]["bar"] == pytest.approx(100 / 3)   # |-1%| against the 3% leader
    assert rows["Energy"]["ret_1m"] != rows["Energy"]["ret_1m"]                            # unknown stays NaN, never a made-up 0


def test_internals_survive_an_empty_market():
    net = marketview.internals([], None)
    assert net["tracked"] == 0 and net["sectors"] == []


def test_series_returns_dates_and_closes_per_index_and_skips_short_or_missing_history(monkeypatch):
    days = pd.bdate_range("2025-01-01", periods=40)
    frames = {BENCHMARK: pd.DataFrame({"Close": range(100, 140)}, index=days),
              VIX: pd.DataFrame({"Close": [15.0] * 10}, index=days[:10])}      # too short to chart
    monkeypatch.setattr(data, "load_ohlcv", frames.get)                         # every other index: no data stored
    out = marketview.series()
    assert [s["symbol"] for s in out] == [BENCHMARK] and out[0]["name"] == INDICES[BENCHMARK]
    assert out[0]["t"][0] == "2025-01-01" and out[0]["v"][:2] == [100.0, 101.0] and len(out[0]["t"]) == len(out[0]["v"]) == 40


def test_series_keeps_only_the_window_the_charts_can_show(monkeypatch):
    days = pd.bdate_range("2020-01-01", periods=marketview.SERIES_SESSIONS + 100)
    monkeypatch.setattr(data, "load_ohlcv", lambda symbol: pd.DataFrame({"Close": range(len(days))}, index=days) if symbol == BENCHMARK else None)
    assert len(marketview.series()[0]["v"]) == marketview.SERIES_SESSIONS


needs_cache = pytest.mark.skipif(data.last_refresh() is None, reason="run a refresh first")


@needs_cache
def test_market_overview_page_has_the_cards_the_charts_and_the_internals():
    page = TestClient(app).get("/market").text
    for needle in ('id="compare-chart"', 'id="index-chart"', 'id="market-ranges"', "renderMarkets(", "Sectors today"):
        assert needle in page
    assert f'data-index="{BENCHMARK}"' in page and 'href="/market"' in page   # the card, and the header link
