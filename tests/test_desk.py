"""Order desk: the browser can't change a price, side or size; risk is capped; no duplicates; dry run only."""

import json
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.broker import desk
from app.research import signal_record
from app.tradeplan import TradePlan

NOW = datetime(2026, 10, 26, 10, 0)
PLAN = TradePlan(entry=100.0, stop=95.0, target1=110.0, target2=115.0, stop_basis="test")
REF = (100.0, "test open")
MISSING_MASTER = (desk.Instrument("TEST-EQ", "UNKNOWN", desk.PLACEHOLDER_TICK), False, "placeholder")


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "BROKER_DIR", tmp_path)
    monkeypatch.setattr(desk, "JOURNAL", tmp_path / "orders.jsonl")
    monkeypatch.setattr(desk, "SCRIP_MASTER", tmp_path / "scrip_master.json")


def swing(verdict="Buy"):
    return SimpleNamespace(verdict=verdict, plan=PLAN)


def intraday(verdict="Long setup"):
    return SimpleNamespace(verdict=verdict, best=SimpleNamespace(plan=PLAN))


def draft(report=None, mode="swing", qty=None, risk=1.0, capital=100_000, ref=REF):
    return desk.build_draft(mode, "TEST.NS", report or swing(), ref, capital, risk, qty, inst=MISSING_MASTER)


def test_buy_gets_a_full_ticket_sized_by_risk():
    d = draft()
    assert d.can_place and d.side == "BUY"
    assert d.max_qty == d.qty == 200          # Rs 1,000 risk / Rs 5 per share
    assert d.rupees_at_risk == pytest.approx(1000)
    assert len(d.ticket.exits) == 2 and d.ticket.entry["producttype"] == "DELIVERY"


def test_only_validated_verdicts_can_be_placed():
    for verdict in ("Watchlist", "Hold", "Avoid"):
        d = draft(swing(verdict))
        assert not d.can_place and verdict in d.ticket.skip
    assert not draft(intraday("Long candidate"), mode="intraday").can_place


def test_intraday_uses_the_intraday_product():
    d = draft(intraday(), mode="intraday")
    assert d.can_place and d.ticket.entry["producttype"] == "INTRADAY"


def test_risk_is_capped_at_one_percent_and_says_so():
    d = draft(risk=5.0)
    assert d.risk_pct == 1.0 and d.qty == 200
    assert any("capped" in n for n in d.notes)


def test_quantity_can_shrink_but_never_grow():
    assert draft(qty=1).qty == 1
    big = draft(qty=10_000)
    assert big.qty == big.max_qty == 200
    assert any("limited" in n for n in big.notes)


def test_no_quantity_when_the_stop_is_wider_than_the_capital_allows():
    d = draft(capital=100)                     # one share costs more than the capital
    assert d.qty == 0 and not d.can_place and "quantity is 0" in d.ticket.skip


def test_open_beyond_the_target_is_skipped_like_the_backtest():
    d = draft(ref=(111.0, "gapped"))
    assert not d.can_place and "at or beyond" in d.ticket.skip


def test_record_writes_the_journal_once_per_day():
    row = desk.record(draft(), NOW)
    assert row["dry_run"] is True and row["id"] == 1
    saved = json.loads(desk.JOURNAL.read_text().strip())
    assert saved["entry"]["transactiontype"] == "BUY" and saved["qty"] == 200
    with pytest.raises(desk.OrderRefused, match="already recorded"):
        desk.record(draft(), NOW)
    assert desk.record(draft(), datetime(2026, 10, 27, 10, 0))["id"] == 2   # a new day is a new order
    assert [o["id"] for o in desk.recent_orders()] == [2, 1]


def test_refused_drafts_are_not_recorded():
    with pytest.raises(desk.OrderRefused, match="Watchlist"):
        desk.record(draft(swing("Watchlist")), NOW)
    assert not desk.JOURNAL.exists()


def test_without_scrip_master_the_token_is_a_flagged_placeholder():
    inst, verified, note = desk.load_instrument("RELIANCE.NS")
    assert (inst.tradingsymbol, inst.token, verified) == ("RELIANCE-EQ", "UNKNOWN", False) and "placeholder" in note


def test_scrip_master_gives_a_verified_instrument():
    desk.SCRIP_MASTER.write_text(json.dumps([
        {"exch_seg": "NSE", "symbol": "RELIANCE-EQ", "token": "2885", "tick_size": "5.000000"},
        {"exch_seg": "BSE", "symbol": "RELIANCE-EQ", "token": "999", "tick_size": "1.000000"}]))
    inst, verified, note = desk.load_instrument("RELIANCE.NS")
    assert (inst.token, inst.tick, verified, note) == ("2885", desk.Decimal("0.05"), True, "")


# ---------- per-signal track record ----------

def _frame(signal_to_fwd, weeks=120, stocks=40):
    rng = np.random.default_rng(3)
    rows = []
    for week in range(weeks):
        points = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0], stocks)
        rows.append(pd.DataFrame({"date": week, "t_rsi_14": points, "fwd": signal_to_fwd(points, rng)}))
    return pd.concat(rows, ignore_index=True)


def test_track_record_detects_a_planted_edge_and_ignores_noise():
    edge = signal_record.compute(_frame(lambda p, rng: 0.05 * p + rng.normal(0, 0.05, len(p))))
    noise = signal_record.compute(_frame(lambda p, rng: rng.normal(0, 0.05, len(p))))
    backwards = signal_record.compute(_frame(lambda p, rng: -0.05 * p + rng.normal(0, 0.05, len(p))))
    assert edge["RSI (14)"]["status"] == "edge"
    assert noise["RSI (14)"]["status"] == "none"
    assert backwards["RSI (14)"]["status"] == "wrong way"


def test_track_record_needs_enough_weeks():
    short = signal_record.compute(_frame(lambda p, rng: p * 1.0, weeks=30))
    assert short["RSI (14)"]["status"] == "insufficient"


def test_describe_handles_missing_records():
    assert "Not backtested" in signal_record.describe(None)
    assert "no proven edge" in signal_record.describe({"status": "none", "ic": -0.02, "t": -1.2, "weeks": 100})
    assert signal_record.bar() > 3.0          # Bonferroni over 23 signals is stricter than 1.96
