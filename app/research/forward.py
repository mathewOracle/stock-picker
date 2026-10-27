"""Forward test of momentum on U2 (docs/SWING_RESEARCH_PLAN.md, Addendum B).

Every ~20 sessions the M1/M2/M6 picks are ranked from the latest COMPLETED session and appended to a git-tracked
CSV before the holding period starts. Nothing here can edit or back-fill a recorded row, so whatever the
evaluation says later was decided before its outcome existed.
"""

import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from app import data
from app.market import MARKET
from app.research import u2
from app.research.factors import FAMILIES, MIN_NAMES, MIN_T, STEP, WARMUP, features, passes, portfolio, stats, top_quintile

PICKS_PATH = MARKET.docs_dir / "forward" / "momentum_picks.csv"   # git-tracked, per market
TZ = MARKET.clock.tz
SETTLED_AFTER, SESSION_OPEN = MARKET.clock.settled_after, MARKET.clock.open
MIN_COVERAGE, MAX_STALE_DAYS, VERDICT_PERIODS = 0.90, 5, 15
TRACKED = {"M1": "M1 12-1 momentum", "M2": "M2 6-1 momentum", "M6": "M6 risk-adjusted momentum"}
FEATURES = [FAMILIES[name][0] for name in TRACKED.values()]
FLAGS = {name: f"pick_{key}" for key, name in TRACKED.items()}


class NotDue(Exception):
    """No rebalance can be recorded right now; the message says why (shown to the user)."""


# ---------- sessions ----------

def calendar(histories: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Exchange sessions = days on which at least half of the stocks traded (holidays fall out on their own)."""
    counts = pd.concat([h.index.to_series() for h in histories.values()]).value_counts()
    return pd.DatetimeIndex(sorted(counts[counts >= len(histories) / 2].index))


def last_completed(cal: pd.DatetimeIndex, now: datetime) -> pd.Timestamp | None:
    """Latest session whose closing prices are final at `now` (a bar from a live session is not)."""
    today = now.astimezone(TZ)
    done = [d for d in cal if d.date() < today.date() or (d.date() == today.date() and today.time() >= SETTLED_AFTER)]
    return done[-1] if done else None


def holding(cal: pd.DatetimeIndex, recorded_at: datetime) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """(entry, exit): entry = first session opening AFTER the picks were recorded; exit = 20 sessions later."""
    later = [i for i, d in enumerate(cal) if datetime.combine(d.date(), SESSION_OPEN, TZ) > recorded_at]
    if not later:
        return None, None
    pos = later[0]
    return cal[pos], (cal[pos + STEP - 1] if pos + STEP - 1 < len(cal) else None)


# ---------- recording ----------

def load_picks(path: Path = PICKS_PATH) -> pd.DataFrame | None:
    return pd.read_csv(path, parse_dates=["signal"]) if path.exists() else None


def _traded(history: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.DataFrame:
    return history[history["Volume"] > 0].reindex(cal)       # same calendar for all; gaps stay NaN


def snapshot(histories: dict[str, pd.DataFrame], cal: pd.DatetimeIndex, signal: pd.Timestamp) -> pd.DataFrame:
    """Eligible stocks with their features at the signal close, ranked. Raises NotDue on a thin data day."""
    upto = cal[cal <= signal]
    rows, active = [], 0
    for symbol, history in histories.items():
        h = _traded(history.loc[:signal], upto)                  # nothing after the signal can leak in
        if h["Close"].notna().sum() < WARMUP or h["Close"].iloc[-STEP:].isna().all():
            continue                                              # too young, or stopped trading a while ago
        active += 1
        f = features(h["Close"].ffill()).iloc[-1][FEATURES]
        if pd.notna(h["Close"].iloc[-1]) and f.notna().all():
            rows.append({"symbol": symbol, **f.to_dict()})
    if active == 0 or len(rows) / active < MIN_COVERAGE or len(rows) < MIN_NAMES:
        raise NotDue(f"Only {len(rows)} of {active} active U2 stocks have a bar on {signal:%d %b %Y}: "
                     "the price refresh looks incomplete. Nothing recorded; try again later.")
    snap = pd.DataFrame(rows)
    for name, flag in FLAGS.items():
        snap[flag] = snap["symbol"].isin(top_quintile(snap, name)["symbol"]).astype(int)
    return snap


def next_signal(picks: pd.DataFrame | None, cal: pd.DatetimeIndex, now: datetime) -> pd.Timestamp:
    """The session to rank on now, or NotDue if the previous holding period is still running."""
    signal = last_completed(cal, now)
    if signal is None or (now.astimezone(TZ).date() - signal.date()).days > MAX_STALE_DAYS:
        raise NotDue("Price data is stale (no completed session in the last few days). Refresh and try again.")
    if picks is not None and not picks.empty:
        _, exit_day = holding(cal, datetime.fromisoformat(picks["recorded_at"].iloc[-1]))
        if exit_day is None or exit_day > signal:
            when = f"after the close of {exit_day:%d %b %Y}" if exit_day is not None else "once the current period ends"
            raise NotDue(f"Current holding period still running; next rebalance is due {when}.")
    return signal


def record(histories: dict[str, pd.DataFrame], now: datetime, path: Path = PICKS_PATH) -> pd.DataFrame:
    """Rank and APPEND one rebalance (existing bytes are never rewritten). Raises NotDue if not due."""
    cal = calendar(histories)
    picks = load_picks(path)
    signal = next_signal(picks, cal, now)
    snap = snapshot(histories, cal, signal)
    snap.insert(0, "recorded_at", now.astimezone(TZ).isoformat(timespec="seconds"))
    snap.insert(0, "signal", signal.strftime("%Y-%m-%d"))
    path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_csv(path, mode="a", header=not path.exists(), index=False, float_format="%.6f")
    return snap


# ---------- evaluation ----------

def _period_return(history: pd.DataFrame, entry: pd.Timestamp, exit_day: pd.Timestamp) -> float:
    """Open of the first traded bar in the window -> close of the last one (delisted = exits at last close)."""
    window = history[history["Volume"] > 0].loc[entry:exit_day]
    return float("nan") if window.empty else float(window["Close"].iloc[-1] / window["Open"].iloc[0] - 1)


def _recorded(flag: str):
    return lambda group, family: group[group[flag] == 1]


def evaluate(picks: pd.DataFrame | None, histories: dict[str, pd.DataFrame], now: datetime) -> dict:
    """Interim (or, after VERDICT_PERIODS, final) scores of the recorded picks."""
    out = {"verdict_periods": VERDICT_PERIODS, "rebalances": [], "families": [], "current": None}
    if picks is None or picks.empty:
        return out
    cal = calendar(histories)
    through = last_completed(cal, now)
    panel = []
    for n, (signal, group) in enumerate(picks.groupby("signal", sort=True)):
        recorded_at = group["recorded_at"].iloc[0]
        entry, exit_day = holding(cal, datetime.fromisoformat(recorded_at))
        done = exit_day is not None and through is not None and exit_day <= through
        rets = ({s: _period_return(histories[s], entry, exit_day) if s in histories else float("nan")
                 for s in group["symbol"]} if done else {})
        out["rebalances"].append({"signal": f"{signal:%Y-%m-%d}", "recorded_at": recorded_at,
                                  "entry": entry and f"{entry:%Y-%m-%d}", "exit": exit_day and f"{exit_day:%Y-%m-%d}",
                                  "complete": done, "eligible": len(group),
                                  "dropped": sum(pd.isna(r) for r in rets.values())})
        if done:
            panel.append(group.assign(n=n, ret=group["symbol"].map(rets)).dropna(subset=["ret"]))
    latest = picks[picks["signal"] == picks["signal"].max()]
    out["current"] = {**out["rebalances"][-1],
                      "picks": {key: sorted(latest.loc[latest[FLAGS[name]] == 1, "symbol"].map(MARKET.short_symbol))
                                for key, name in TRACKED.items()}}
    full = pd.concat(panel, ignore_index=True) if panel else None
    for key, name in TRACKED.items():
        out["families"].append(_family(key, name, full))
    return out


def _family(key: str, name: str, panel: pd.DataFrame | None) -> dict:
    if panel is None:
        return {"key": key, "name": name, "periods": 0, "status": "interim"}
    res = portfolio(panel, name, pick=_recorded(FLAGS[name]))
    doubled = portfolio(panel, name, cost_mult=2.0, pick=_recorded(FLAGS[name]))
    if len(res) < VERDICT_PERIODS:
        return {"key": key, "name": name, **stats(res), "periods": len(res), "status": "interim"}
    # ONE look: the verdict is frozen on the first VERDICT_PERIODS periods; later ones never change it
    s, d = stats(res.iloc[:VERDICT_PERIODS]), stats(doubled.iloc[:VERDICT_PERIODS])
    ok = passes(s, MIN_T) and d["net"] > 0
    return {"key": key, "name": name, **s, "double_net": d["net"], "status": "PASS" if ok else "fail"}


# ---------- the job ----------

def run(progress: data.Progress = data._no_progress, now: datetime | None = None, path: Path = PICKS_PATH) -> dict:
    """Refresh U2 -> record a rebalance if one is due -> evaluate everything recorded so far."""
    started = time.time()
    try:
        missing, refreshed = u2.refresh(progress), True
    except data.RefreshError as exc:
        missing, refreshed, note = [], False, f"{exc} Nothing recorded."
    histories = {s: h for s in u2.SYMBOLS if (h := u2.load(s)) is not None}
    if not histories:
        raise data.RefreshError("No U2 price history on disk yet; run `python -m scripts.fetch_extra_universe`.")
    now = now or datetime.now(TZ)
    if refreshed:   # ranking on prices that were not refreshed in this very run is not allowed
        try:
            snap = record(histories, now, path)
            note = (f"Recorded a new rebalance on {snap['signal'].iloc[0]} ({len(snap)} eligible stocks). "
                    f"Commit {path.name} so the record is timestamped.")
        except NotDue as exc:
            note = str(exc)
    result = {**evaluate(load_picks(path), histories, now), "note": note, "missing": missing,
              "generated_at": time.time(), "seconds": round(time.time() - started, 1)}
    data.save_result("forward", result)
    return result
