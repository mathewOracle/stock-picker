"""Smoke tests for the web layer. They use the SQLite cache if present, never the network."""

import pytest
from fastapi.testclient import TestClient

from app import data, main
from app.data import RefreshResult
from app.jobs import RefreshJob
from app.main import app, crore, pct, pe

client = TestClient(app)
needs_cache = pytest.mark.skipif(data.last_refresh() is None, reason="run a refresh first")


def test_formatters_handle_nan_and_loss():
    assert pct(float("nan")) == "–"
    assert pct(0.1234) == "+12.3%"
    assert pe(1000.0) == "loss"
    assert crore(None) == "–"


def test_unknown_symbol_is_404():
    assert client.get("/stock/NOPE.NS").status_code == 404


def test_vendored_assets_are_served():
    for path in ("/static/app.css", "/static/vendor/htmx.min.js", "/static/vendor/lightweight-charts.js",
                 "/static/charts.js", "/static/position-size.js"):
        assert client.get(path).status_code == 200


def test_responses_are_gzipped():
    response = client.get("/static/charts.js", headers={"Accept-Encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip"


def test_unknown_job_is_404():
    assert client.post("/refresh/nope").status_code == 404


def test_refresh_failure_shows_error(monkeypatch):
    def broken(progress):
        raise RuntimeError("Could not reach Yahoo Finance")

    monkeypatch.setitem(main.jobs, "daily", RefreshJob(broken))
    client.post("/refresh/daily")
    for _ in range(100):
        response = client.get("/refresh/daily/status")
        if "failed" in response.text:
            break
    assert "Refresh failed" in response.text and "HX-Refresh" not in response.headers


def test_refresh_success_triggers_reload(monkeypatch):
    monkeypatch.setitem(main.jobs, "intraday", RefreshJob(lambda progress: RefreshResult(1, [], 0.1)))
    client.post("/refresh/intraday")
    for _ in range(100):
        response = client.get("/refresh/intraday/status")
        if response.headers.get("HX-Refresh"):
            break
    assert response.headers.get("HX-Refresh") == "true"


@needs_cache
def test_dashboard_and_table_render():
    page = client.get("/")
    assert page.status_code == 200 and "Suggested buys" in page.text and "Watchlist" in page.text
    assert client.get("/table", params={"verdict": "Avoid"}).status_code == 200


@needs_cache
def test_stock_detail_renders_all_pillars():
    page = client.get("/stock/RELIANCE.NS")
    assert page.status_code == 200
    for section in ("Fundamental analysis", "Technical analysis", "Chart analysis", "Trade plan", "Decision checklist"):
        assert section in page.text
    # the swing plan is sized and spelled out on the page itself, with the same sizer as intraday
    for piece in ('id="sizer"', "data-qty", "/static/position-size.js", "How to enter and exit"):
        assert piece in page.text


def test_swing_steps_trade_the_plan_exactly_as_the_backtest_does():
    from types import SimpleNamespace

    from app.research.backtest import MAX_HOLD

    plan = SimpleNamespace(entry=2000.0, stop=1900.0, target1=2200.0, target2=2300.0)
    text = str(main.templates.env.get_template("_macros.html").module.swing_entry_exit_steps(plan))
    assert "next session's open" in text and "delivery (CNC)" in text            # backtest: enter at the next open
    assert "1,900.00" in text and "2,200.00" in text and "whole quantity" in text  # stop / T1 for everything
    assert f"close of session {MAX_HOLD}" in text                                 # time exit = MAX_HOLD, not a copy
    assert "sells everything at T1" in text and "GTT" in text                     # T2 is not presented as the plan


needs_intraday = pytest.mark.skipif(data.last_intraday_refresh() is None, reason="run an intraday refresh first")


@needs_intraday
def test_intraday_pages_render():
    page = client.get("/intraday")
    assert page.status_code == 200
    for section in ("Intraday scanner", "Active setups", "Scanner", "Intraday playbook", "risk rules"):
        assert section in page.text
    detail = client.get("/intraday/RELIANCE.NS")
    assert detail.status_code == 200 and "Key levels" in detail.text and "Next session" in detail.text
    assert client.get("/intraday/NOPE.NS").status_code == 404


@needs_intraday
def test_intraday_setup_pages_show_backtest_evidence():
    """Every detected setup must say whether the backtest actually supports it, not just what triggered it."""
    from app.intraday import analysis as intraday

    scan = intraday.build()
    report = next((r for r in scan.reports if r.setups), None)
    if report is None:
        pytest.skip("no stock currently has a detected setup")
    page = client.get(f"/intraday/{report.symbol}").text
    evidence_words = ("supported", "not supported", "insufficient data", "not backtested", "never fired")
    assert any(word in page for word in evidence_words)
    # the scanner table and active-setups cards both reuse the same evidence badge
    scanner = client.get("/intraday").text
    assert any(word in scanner for word in evidence_words)
