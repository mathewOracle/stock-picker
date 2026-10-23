"""Descriptive (plan section 'Also measured'): do the existing 5-minute setups survive once costs stop dominating?

Same entries as the live backtest; only the exits change: stop at least 0.8 % from entry (round-trip cost <= 0.15 R),
no target, square-off at 15:15. 60 sessions only, so this is reported, never adopted.

Usage: .venv/bin/python -m scripts.intraday_geometry_probe
"""

from concurrent.futures import ProcessPoolExecutor
from functools import partial

import pandas as pd

from app.intraday import archive
from app.research import intraday_backtest as ib
from app.universe import STOCKS

MIN_STOP = 0.008


def wide_levels(setup) -> tuple[float, float]:
    entry, sign = setup.plan.entry, 1 if setup.side == "Long" else -1
    stop = min(setup.plan.stop, entry * (1 - MIN_STOP)) if sign > 0 else max(setup.plan.stop, entry * (1 + MIN_STOP))
    return stop, entry * (10 if sign > 0 else 0.1)              # unreachable target -> exit at stop or square-off


def replay(symbol: str) -> list[dict]:
    raw = archive.load(symbol)
    return [] if raw is None else ib.replay_symbol(symbol, raw, levels=wide_levels)["trades"]


def main() -> None:
    with ProcessPoolExecutor(max_workers=ib.WORKERS) as pool:
        wide = pd.DataFrame([t for trades in pool.map(replay, STOCKS) for t in trades])
    base = ib.load_ledger()
    print(f"{'setup':24}{'n':>6}{'base net':>10}{'base t':>8}{'wide net':>10}{'wide gross':>11}{'wide t':>8}{'cost R':>8}")
    for key in sorted(set(base["setup"] + ":" + base["side"])):
        setup, side = key.split(":")
        b = base[(base["setup"] == setup) & (base["side"] == side)]
        w = wide[(wide["setup"] == setup) & (wide["side"] == side)]
        if len(w) < 30:
            continue
        bt, wt = ib.day_clustered_t(b)[0], ib.day_clustered_t(w)[0]
        risk = (w["net_return"] / w["r_multiple"]).abs().median()
        print(f"{key:24}{len(w):>6}{b['net_return'].mean():>+10.3%}{bt:>8.2f}{w['net_return'].mean():>+10.3%}"
              f"{w['net_return'].mean() + 2 * ib.COST_PER_SIDE:>+11.3%}{wt:>8.2f}{2 * ib.COST_PER_SIDE / risk:>8.2f}")
    t, days = ib.day_clustered_t(wide)
    print(f"{'ALL (wide)':24}{len(wide):>6}{'':>18}{wide['net_return'].mean():>+10.3%}"
          f"{wide['net_return'].mean() + 2 * ib.COST_PER_SIDE:>+11.3%}{t:>8.2f}   over {days} sessions")


if __name__ == "__main__":
    main()
