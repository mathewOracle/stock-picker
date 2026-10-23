"""Price-only stock rankings vs the universe average, run EXACTLY as docs/SWING_RESEARCH_PLAN.md says.

Gates are enforced in code: validation (V) only runs for families that passed discovery (D), confirmation (C)
only for families that passed V. The regime overlay is descriptive and only printed for C survivors.

Usage: .venv/bin/python -m scripts.swing_factor_probe            # the app's 63 stocks (main plan)
       .venv/bin/python -m scripts.swing_factor_probe extra      # Addendum A's independent universe
"""

import math
import sys

import pandas as pd

from app import data
from app.research.factors import FAMILIES, MIN_T, POSITIVE_SHARE, STEP, WARMUP, features, passes, portfolio, stats
from app.universe import BENCHMARK, STOCKS

D_END, V_END = "2021-12-31", "2024-10-31"
C_MIN_T = 1.0


def build_periods(symbols=STOCKS, load=data.load_history) -> pd.DataFrame:
    """One row per (rebalance, stock): the features at the signal close and the realised 20-session return."""
    nifty = data.load_history(BENCHMARK)["Close"]
    calendar = nifty.index
    signal_pos = list(range(WARMUP, len(calendar) - STEP - 1, STEP))
    rows = []
    for symbol in symbols:
        h = load(symbol)
        if h is None:
            continue
        h = h[h["Volume"] > 0].reindex(calendar)            # same calendar as the benchmark; gaps stay NaN
        feats = features(h["Close"].ffill())
        for n, pos in enumerate(signal_pos):
            entry_day, exit_day = calendar[pos + 1], calendar[pos + STEP]
            o, c = h["Open"].iloc[pos + 1], h["Close"].iloc[pos + STEP]
            f = feats.iloc[pos]
            if math.isnan(o) or math.isnan(c) or f.isna().any() or math.isnan(h["Close"].iloc[pos]):
                continue
            rows.append({"n": n, "signal": calendar[pos], "symbol": symbol, "ret": c / o - 1, **f.to_dict(),
                         "nifty_above_200": bool(nifty.iloc[pos] > nifty.iloc[pos - 199: pos + 1].mean())})
    return pd.DataFrame(rows)


def max_drawdown(period_returns: pd.Series) -> float:
    curve = (1 + period_returns).cumprod()
    return float((curve / curve.cummax() - 1).min())


def line(label: str, s: dict, verdict: str = "") -> str:
    if s.get("periods", 0) < 3:
        return f"  {label:34} too few periods ({s.get('periods', 0)})"
    return (f"  {label:34}{s['periods']:>5}{s['top']:>+8.2%}{s['universe']:>+8.2%}{s['gross']:>+8.2%}{s['net']:>+8.2%}"
            f"{s['t']:>6.2f}{s['pos']:>6.0%}{s['turnover']:>6.0%}  {verdict}")


HEADER = f"  {'family':34}{'per.':>5}{'top':>8}{'univ.':>8}{'grossx':>8}{'netx':>8}{'t':>6}{'yr+':>6}{'turn':>6}"


def main(universe: str = "app") -> None:
    if universe == "extra":
        from app.research import u2
        panel = build_periods(u2.SYMBOLS, u2.load)
    else:
        panel = build_periods()
    disc = panel[panel["signal"] <= D_END]
    valid = panel[(panel["signal"] > D_END) & (panel["signal"] <= V_END)]
    conf = panel[panel["signal"] > V_END]
    print(f"{panel['n'].nunique()} rebalances, {panel['symbol'].nunique()} stocks, "
          f"{panel['signal'].min():%Y-%m-%d} to {panel['signal'].max():%Y-%m-%d}")

    print(f"\nD: discovery to {D_END} (pass: net excess > 0, t >= {MIN_T}, >= {POSITIVE_SHARE:.0%} of years positive)\n{HEADER}")
    survivors = []
    for family in FAMILIES:
        s = stats(portfolio(disc, family))
        survivors += [family] if passes(s, MIN_T) else []
        print(line(family, s, "PASS" if passes(s, MIN_T) else "fail"))
    if not survivors:
        print("\nNo family passed discovery: validation and confirmation stay closed (as pre-registered).")
        return

    print(f"\nV: validation {D_END} to {V_END}, survivors only (also > 0 at double cost)\n{HEADER}")
    finalists = []
    for family in survivors:
        s, doubled = stats(portfolio(valid, family)), stats(portfolio(valid, family, cost_mult=2.0))
        ok = passes(s, MIN_T) and doubled.get("net", -1) > 0
        finalists += [family] if ok else []
        print(line(family, s, f"{'PASS' if ok else 'fail'} (net at 2x cost {doubled.get('net', float('nan')):+.2%})"))
    if not finalists:
        print("\nNo family passed validation: confirmation stays closed (as pre-registered).")
        return

    print(f"\nC: confirmation after {V_END}, finalists only (pass: net excess > 0, t >= {C_MIN_T})\n{HEADER}")
    winners = []
    for family in finalists:
        s = stats(portfolio(conf, family))
        ok = passes(s, C_MIN_T, need_years=False)
        winners += [family] if ok else []
        print(line(family, s, "PASS" if ok else "fail"))
    if not winners:
        print("\nNo family passed confirmation.")
        return
    print("\nDescriptive: market-regime overlay (cash when Nifty < 200-DMA), whole history, passing families only")
    for family in winners:
        for label, overlay in (("always invested", False), ("cash below 200-DMA", True)):
            res = portfolio(panel, family, overlay=overlay)
            print(f"  {family:28}{label:20} avg period {res['net_top'].mean():+.2%}  worst fall {max_drawdown(res['net_top']):+.1%}")
        print(f"  {'universe (equal weight)':28}{'':20} avg period {res['universe'].mean():+.2%}  worst fall {max_drawdown(res['universe']):+.1%}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "app")
