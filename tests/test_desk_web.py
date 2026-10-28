"""The order desk as a user meets it: tabs, ranked lists, per-tab research, re-analyse, and the dry-run order flow."""

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import data, deskview
from app.broker import desk
from app.intraday import analysis as intraday
from app.intraday import archive
from app.main import app
from app.tradeplan import TradePlan
from app.universe import STOCKS

client = TestClient(app)
needs_cache = pytest.mark.skipif(data.last_refresh() is None, reason="run a refresh first")
HX = {"HX-Request": "true"}
BUY = SimpleNamespace(verdict="Buy", plan=TradePlan(100.0, 95.0, 110.0, 115.0, "test"), blockers=[])
SYMBOL = next(iter(STOCKS))


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "BROKER_DIR", tmp_path)
    monkeypatch.setattr(desk, "JOURNAL", tmp_path / "orders.jsonl")
    monkeypatch.setattr(desk, "SCRIP_MASTER", tmp_path / "scrip_master.json")


@pytest.fixture
def validated_buy(monkeypatch):
    """No stock passes validation today, so fake one: the flow below is what happens the day one does."""
    monkeypatch.setattr(deskview, "report_for", lambda symbol, tab: BUY)
    monkeypatch.setattr(desk, "swing_reference", lambda symbol: (100.0, "test open"))
    monkeypatch.setattr(deskview, "symbol_freshness", lambda symbol, tab: {"label": "just now", "stale": False, "why": ""})


def numbers(html: str, attribute: str) -> list[float]:
    return [float(v) for v in re.findall(rf'<li id="row-[^"]+"[^>]*? data-{attribute}="([\d.]+)"', html)]


# ---------- the page and its tabs ----------

@needs_cache
def test_home_is_the_order_desk_with_two_tabs_and_research_is_not_a_tab():
    html = client.get("/").text
    assert "Order desk" in html and 'aria-label="Trading style"' in html
    assert 'aria-current="page"' in html and 'id="swing-list"' in html and 'id="detail"' in html
    assert 'hx-get="/research/swing"' in html and "Refresh swing data" in html
    header = html.split("<main")[0]
    assert "Research" not in header and "Swing &amp; positional" not in header      # the old top-level tabs are gone


@needs_cache
def test_intraday_tab_has_buy_and_short_intensity_rank_buttons():
    html = client.get("/?tab=intraday").text
    assert 'id="intraday-list"' in html and 'data-sort="-qualitybuy"' in html and 'data-sort="-qualityshort"' in html
    assert 'hx-get="/research/intraday"' in html and "Refresh intraday data" in html and "Long-leaning" in html


@needs_cache
def test_htmx_gets_the_fragment_but_history_restore_gets_the_page():
    fragment = client.get("/?tab=intraday", headers=HX).text
    assert "<html" not in fragment and 'id="intraday-list"' in fragment
    assert "<html" in client.get("/", headers={**HX, "HX-History-Restore-Request": "true"}).text


@needs_cache
def test_selected_symbol_is_kept_and_a_symbol_the_tab_lacks_falls_back():
    assert f'data-symbol="{SYMBOL}"' in client.get(f"/?tab=swing&symbol={SYMBOL}").text
    assert 'data-symbol="' in client.get(f"/?tab=intraday&symbol={SYMBOL}").text      # never a blank panel


def test_unknown_symbol_and_bad_tab_are_rejected():
    assert client.get("/?symbol=NOPE.NS").status_code == 404
    assert client.get("/?tab=options").status_code == 422
    assert client.get("/detail?tab=swing&symbol=NOPE.NS").status_code == 404


def test_legacy_desk_url_redirects_home():
    response = client.get("/desk?symbol=TCS.NS", follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "/?symbol=TCS.NS"


# ---------- ranking ----------

@needs_cache
def test_swing_list_is_ranked_by_buy_intensity_best_first():
    scores = numbers(client.get("/").text, "intensity")
    assert len(scores) > 10 and scores == sorted(scores, reverse=True)


@needs_cache
@pytest.mark.skipif(not intraday.build().reports, reason="no intraday data cached")
def test_intraday_list_follows_the_rank_choice():
    buy = numbers(client.get("/?tab=intraday&rank=long").text, "buy")
    short = numbers(client.get("/?tab=intraday&rank=short").text, "short")
    buy_quality = numbers(client.get("/?tab=intraday&rank=long").text, "qualitybuy")
    short_quality = numbers(client.get("/?tab=intraday&rank=short").text, "qualityshort")
    assert buy_quality == sorted(buy_quality, reverse=True) and short_quality == sorted(short_quality, reverse=True)
    assert 'aria-pressed="true"' in client.get("/?tab=intraday&rank=short").text


@needs_cache
def test_detail_panel_is_the_selected_stock_only():
    html = client.get(f"/detail?tab=swing&symbol={SYMBOL}").text
    assert f'data-symbol="{SYMBOL}"' in html and "<html" not in html and 'id="signal-list"' in html and "Re-analyse" in html


# ---------- research lives on each tab ----------

def test_research_panel_shows_only_that_sides_evidence():
    swing, live = client.get("/research/swing").text, client.get("/research/intraday").text
    assert "Backtest of the price rules" in swing and "Forward test" in swing and "Intraday setups backtest" not in swing
    assert "Intraday setups backtest" in live and "Backtest of the price rules" not in live
    assert 'id="research-title"' in swing and "Research &amp; validation: Swing" in swing
    assert client.get("/research/options").status_code == 422


def test_full_research_page_still_has_everything():
    page = client.get("/research").text
    assert all(text in page for text in ("Backtest of the price rules", "Intraday setups backtest", "Forward test", "How to read this honestly"))


# ---------- re-analyse ----------

@pytest.fixture
def refreshes(monkeypatch):
    calls = []
    monkeypatch.setattr(data, "refresh_symbol", lambda symbol: calls.append(("daily", symbol)))
    monkeypatch.setattr(archive, "refresh_symbol", lambda symbol: calls.append(("intraday", symbol)))
    return calls


@needs_cache
def test_reanalyse_refreshes_that_stock_and_updates_its_row_in_place(refreshes):
    html = client.post(f"/reanalyse?tab=swing&symbol={SYMBOL}", headers=HX).text
    assert refreshes == [("daily", SYMBOL)]
    assert "Re-analysed" in html and f'data-symbol="{SYMBOL}"' in html
    assert f'id="row-{SYMBOL}"' in html and 'hx-swap-oob="true"' in html            # the list row is refreshed too


@needs_cache
@pytest.mark.skipif(not intraday.build().reports, reason="no intraday data cached")
def test_reanalyse_on_the_intraday_tab_pulls_five_minute_bars(refreshes):
    symbol = intraday.build().reports[0].symbol
    assert "Re-analysed" in client.post(f"/reanalyse?tab=intraday&symbol={symbol}", headers=HX).text
    assert refreshes == [("intraday", symbol)]


@needs_cache
def test_failed_reanalysis_says_so_and_keeps_the_page(monkeypatch):
    def broken(symbol):
        raise data.RefreshError("Could not reach Yahoo Finance")
    monkeypatch.setattr(data, "refresh_symbol", broken)
    response = client.post(f"/reanalyse?tab=swing&symbol={SYMBOL}", headers=HX)
    assert response.status_code == 200 and "Re-analysis failed" in response.text and "previous data" in response.text
    assert f'data-symbol="{SYMBOL}"' in response.text and 'role="alert"' in response.text


def test_reanalyse_is_guarded(refreshes):
    assert client.post(f"/reanalyse?tab=swing&symbol={SYMBOL}").status_code == 403       # needs the HTMX header
    assert client.post("/reanalyse?tab=swing&symbol=NOPE.NS", headers=HX).status_code == 404
    assert refreshes == []                                                              # nothing was downloaded


# ---------- the order flow (dry run) ----------

@needs_cache
def test_unplaceable_stock_explains_why_and_has_no_live_button():
    html = client.get("/").text
    if 'hx-get="/desk/ticket' not in html:   # today's reality: nothing validated
        assert "Why not:" in html and "disabled" in html


def test_unknown_mode_is_rejected():
    assert client.get("/desk/ticket?symbol=X.NS&mode=options").status_code == 422


def test_ticket_shows_the_server_built_bodies(validated_buy):
    html = client.get("/desk/ticket?symbol=TEST.NS&mode=swing&capital=100000&risk=1").text
    assert "BUY" in html and "DELIVERY" in html and "Record dry-run order" in html
    assert "placeholder" in html and "Nothing is sent to Angel One" in html
    assert "&#34;transactiontype&#34;: &#34;BUY&#34;" in html or '"transactiontype": "BUY"' in html


def test_ticket_clamps_risk_and_quantity_asked_by_the_browser(validated_buy):
    html = client.get("/desk/ticket?symbol=TEST.NS&mode=swing&capital=100000&risk=50&qty=99999").text
    assert 'max="200"' in html and 'value="200"' in html and "capped" in html


def test_ticket_for_a_non_buy_cannot_be_confirmed(monkeypatch):
    monkeypatch.setattr(deskview, "report_for", lambda symbol, tab: SimpleNamespace(verdict="Watchlist", plan=BUY.plan))
    monkeypatch.setattr(desk, "swing_reference", lambda symbol: (100.0, "test open"))
    html = client.get("/desk/ticket?symbol=TEST.NS&mode=swing").text
    assert "Can't place this order" in html and "Watchlist" in html and "Record dry-run order" not in html


def test_order_needs_the_htmx_header(validated_buy):
    assert client.post("/desk/order?symbol=TEST.NS&mode=swing").status_code == 403
    assert not desk.JOURNAL.exists()


def test_order_is_recorded_once_and_never_duplicated(validated_buy):
    first = client.post("/desk/order?symbol=TEST.NS&mode=swing&qty=5", headers=HX).text
    assert "Recorded dry-run order #1" in first and "Nothing was sent to Angel One" in first
    assert 'hx-swap-oob="true"' in first and "BUY 5" in first          # journal + buttons update in place
    assert 'id="order-card"' in first and "Already recorded today" in first   # ...and so does the order card
    second = client.post("/desk/order?symbol=TEST.NS&mode=swing&qty=5", headers=HX)
    assert second.status_code == 200 and "already recorded" in second.text   # 200: htmx won't swap a 4xx
    assert len(desk.JOURNAL.read_text().splitlines()) == 1


def test_stale_prices_block_the_order_on_the_card_and_on_the_server(validated_buy, monkeypatch):
    stale = {"label": "6 days ago", "stale": True, "why": "Daily prices are 6 days old: re-analyse or refresh before ordering."}
    monkeypatch.setattr(deskview, "symbol_freshness", lambda symbol, tab: stale)
    card = deskview.order_card("TEST.NS", "swing", BUY)
    assert card["blocked"] == stale["why"]
    response = client.post("/desk/order?symbol=TEST.NS&mode=swing&qty=5", headers=HX)   # a hand-made request, past the card
    assert "Not recorded" in response.text and "6 days old" in response.text
    assert not desk.JOURNAL.exists()


@needs_cache
def test_risk_input_cannot_promise_more_than_the_server_allows():
    html = client.get("/").text
    assert f'max="{desk.MAX_RISK_PCT}"' in html and "max 1)" in html


def test_order_quantity_cannot_exceed_the_risk_rule(validated_buy):
    client.post("/desk/order?symbol=TEST.NS&mode=swing&capital=100000&risk=9&qty=99999", headers=HX)
    assert '"qty": 200' in desk.JOURNAL.read_text()


# ---------- the indices panel above the desk ----------

@needs_cache
@pytest.mark.parametrize("tab", ["swing", "intraday"])
def test_the_indices_panel_is_open_at_the_top_of_the_desk_on_either_tab(tab):
    page = client.get(f"/?tab={tab}").text
    assert '<details open class="group">' in page and 'id="compare-chart"' in page
    assert page.index('id="markets-panel"') < page.index('id="desk"')       # above the tabs and the lists


@needs_cache
def test_a_tab_switch_swaps_only_the_desk_so_the_indices_charts_are_not_rebuilt():
    fragment = client.get("/?tab=intraday", headers=HX).text
    assert 'id="markets-panel"' not in fragment and "renderMarkets" not in fragment
