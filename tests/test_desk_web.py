"""Order desk web layer: page, HTMX partials, the ticket dialog, and the dry-run order endpoint."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import data, main
from app.broker import desk
from app.main import app
from app.tradeplan import TradePlan

client = TestClient(app)
needs_cache = pytest.mark.skipif(data.last_refresh() is None, reason="run a refresh first")
HX = {"HX-Request": "true"}
BUY = SimpleNamespace(verdict="Buy", plan=TradePlan(100.0, 95.0, 110.0, 115.0, "test"))


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "BROKER_DIR", tmp_path)
    monkeypatch.setattr(desk, "JOURNAL", tmp_path / "orders.jsonl")
    monkeypatch.setattr(desk, "SCRIP_MASTER", tmp_path / "scrip_master.json")


@pytest.fixture
def validated_buy(monkeypatch):
    """No stock passes validation today, so fake one: the flow below is what happens the day one does."""
    monkeypatch.setattr(main, "_desk_report", lambda symbol, mode: BUY)
    monkeypatch.setattr(desk, "swing_reference", lambda symbol: (100.0, "test open"))


@needs_cache
def test_desk_page_lists_every_signal_with_its_track_record():
    html = client.get("/desk").text
    assert "<html" in html and "Order desk" in html and "Dry run" not in html.split("<main")[0]
    assert 'id="signal-list"' in html and "Track record:" in html and "nothing is sent to a broker" in html.lower()
    assert 'data-pillar="Technical"' in html and 'data-pillar="Fundamental"' in html and 'data-pillar="Chart"' in html


@needs_cache
def test_htmx_request_gets_only_the_panel_but_history_restore_gets_the_page():
    partial = client.get("/desk", headers=HX).text
    assert "<html" not in partial and 'id="signal-list"' in partial
    assert "<html" in client.get("/desk", headers={**HX, "HX-History-Restore-Request": "true"}).text


@needs_cache
def test_unplaceable_stock_explains_why_and_has_no_live_button():
    html = client.get("/desk").text
    if 'hx-get="/desk/ticket' not in html:   # today's reality: nothing validated
        assert "Why not:" in html and "disabled" in html


def test_unknown_symbol_and_mode_are_rejected():
    assert client.get("/desk?symbol=NOPE.NS").status_code == 404
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
    monkeypatch.setattr(main, "_desk_report", lambda symbol, mode: SimpleNamespace(verdict="Watchlist", plan=BUY.plan))
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
    second = client.post("/desk/order?symbol=TEST.NS&mode=swing&qty=5", headers=HX)
    assert second.status_code == 200 and "already recorded" in second.text   # 200: htmx won't swap a 4xx
    assert len(desk.JOURNAL.read_text().splitlines()) == 1


def test_order_quantity_cannot_exceed_the_risk_rule(validated_buy):
    client.post("/desk/order?symbol=TEST.NS&mode=swing&capital=100000&risk=9&qty=99999", headers=HX)
    assert '"qty": 200' in desk.JOURNAL.read_text()
