"""Forward test (Addendum B): the record is append-only, timing can't leak the future, the verdict looks once."""

from datetime import datetime, time

import numpy as np
import pandas as pd
import pytest

from app import data
from app.research import forward, u2
from app.research.factors import top_quintile
from tests.conftest import make_ohlcv

IST = forward.IST


def universe(stocks: int = 40, days: int = 700, seed: int = 3) -> dict[str, pd.DataFrame]:
    """Persistent drifts (stock i drifts with i), so momentum genuinely works here."""
    rng = np.random.default_rng(seed)
    return {f"S{i:02d}.NS": make_ohlcv(100 * np.cumprod(1 + 0.0002 * (i - stocks / 2) + rng.normal(0, 0.01, days)))
            for i in range(stocks)}


def at(day: pd.Timestamp, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day.date(), time(hour, minute), IST)


@pytest.fixture
def histories():
    return universe()


@pytest.fixture
def cal(histories):
    return forward.calendar(histories)


def test_a_live_session_is_not_a_completed_one(cal):
    day = cal[300]
    assert forward.last_completed(cal, at(day, 15, 0)) == cal[299]     # market still open
    assert forward.last_completed(cal, at(day, 16, 5)) == day


def test_entry_is_the_first_open_after_recording(cal):
    day = cal[300]
    assert forward.holding(cal, at(day, 20))[0] == cal[301]            # evening -> next morning
    assert forward.holding(cal, at(cal[301], 8))[0] == cal[301]        # before the open -> that open
    entry, exit_day = forward.holding(cal, at(cal[301], 10))           # after the open -> too late for it
    assert entry == cal[302] and exit_day == cal[302 + forward.STEP - 1]


def test_record_is_append_only_and_waits_for_the_exit(histories, cal, tmp_path):
    path = tmp_path / "picks.csv"
    first = forward.record(histories, at(cal[300], 20), path)
    assert first["signal"].iloc[0] == f"{cal[300]:%Y-%m-%d}"
    before = path.read_bytes()
    with pytest.raises(forward.NotDue, match="still running"):
        forward.record(histories, at(cal[310], 20), path)
    assert path.read_bytes() == before                                 # a refusal writes nothing
    exit_day = cal[301 + forward.STEP - 1]
    forward.record(histories, at(exit_day, 20), path)
    after = path.read_bytes()
    assert after.startswith(before) and len(after) > len(before)       # old bytes untouched, new ones appended
    assert list(forward.load_picks(path)["signal"].unique()) == [cal[300], exit_day]


def test_a_thin_data_day_is_refused_not_recorded_small(histories, cal, tmp_path):
    signal = cal[300]
    for symbol in list(histories)[:8]:                                 # 20% missing the signal bar
        histories[symbol] = histories[symbol].drop(signal)
    with pytest.raises(forward.NotDue, match="incomplete"):
        forward.record(histories, at(signal, 20), tmp_path / "picks.csv")
    assert not (tmp_path / "picks.csv").exists()


def test_stale_prices_are_refused(histories, cal, tmp_path):
    cut = {s: h.loc[:cal[300]] for s, h in histories.items()}
    with pytest.raises(forward.NotDue, match="stale"):
        forward.record(cut, at(cal[300] + pd.Timedelta(days=10), 20), tmp_path / "picks.csv")


def test_ranking_uses_nothing_after_the_signal(histories, cal):
    signal = cal[400]
    cut = {s: h.loc[:signal] for s, h in histories.items()}
    full = forward.snapshot(histories, cal, signal)
    pd.testing.assert_frame_equal(full, forward.snapshot(cut, forward.calendar(cut), signal))


def test_recorded_flags_are_the_top_quintile(histories, cal):
    snap = forward.snapshot(histories, cal, cal[400])
    for name, flag in forward.FLAGS.items():
        assert set(snap.loc[snap[flag] == 1, "symbol"]) == set(top_quintile(snap, name)["symbol"])
    assert snap[list(forward.FLAGS.values())].sum().eq(len(snap) // 5).all()


def test_a_delisted_stock_exits_at_its_last_close():
    h = make_ohlcv([100, 110, 120, 90])
    days = h.index
    assert forward._period_return(h, days[1], days[3]) == pytest.approx(90 / h["Open"].iloc[1] - 1)
    gone = h.iloc[:3]                                                  # stops trading before the exit day
    assert forward._period_return(gone, days[1], days[3]) == pytest.approx(120 / h["Open"].iloc[1] - 1)
    assert np.isnan(forward._period_return(h.iloc[:1], days[1], days[3]))


def test_nothing_recorded_means_nothing_scored(histories):
    assert forward.evaluate(None, histories, datetime.now(IST))["families"] == []


def simulate(histories, cal, path, last: int):
    """Run the job every evening, like someone pressing the button daily."""
    for day in cal[260: last]:
        try:
            forward.record(histories, at(day, 20), path)
        except forward.NotDue:
            pass


def test_interim_until_fifteen_periods_then_one_frozen_look(histories, cal, tmp_path):
    path = tmp_path / "picks.csv"
    simulate(histories, cal, path, last=len(cal))
    picks = forward.load_picks(path)
    out = forward.evaluate(picks, histories, at(cal[-1], 20))
    done = [r for r in out["rebalances"] if r["complete"]]
    assert len(done) > forward.VERDICT_PERIODS                         # more periods exist than the verdict uses
    spans = [(pd.Timestamp(r["entry"]), pd.Timestamp(r["exit"])) for r in done]
    assert all(prev[1] < nxt[0] for prev, nxt in zip(spans, spans[1:]))   # holding periods never overlap
    for fam in out["families"]:
        assert fam["periods"] == forward.VERDICT_PERIODS and fam["status"] == "PASS"   # planted edge found
    assert sorted(out["current"]["picks"]) == ["M1", "M2", "M6"]

    early = picks[picks["signal"] <= pd.Timestamp(done[4]["signal"])]
    interim = forward.evaluate(early, histories, at(cal[-1], 20))
    assert {f["status"] for f in interim["families"]} == {"interim"}


def test_job_records_only_on_prices_refreshed_in_the_same_run(histories, cal, tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(u2, "SYMBOLS", list(histories))
    monkeypatch.setattr(u2, "load", histories.get)
    path = tmp_path / "picks.csv"

    def offline(progress):
        raise data.RefreshError("Yahoo unreachable.")
    monkeypatch.setattr(u2, "refresh", offline)
    result = forward.run(now=at(cal[300], 20), path=path)
    assert "Nothing recorded" in result["note"] and not path.exists()

    monkeypatch.setattr(u2, "refresh", lambda progress: [])
    result = forward.run(now=at(cal[300], 20), path=path)
    assert "Recorded a new rebalance" in result["note"] and path.exists()
    assert data.load_result("forward")["current"]["signal"] == f"{cal[300]:%Y-%m-%d}"
