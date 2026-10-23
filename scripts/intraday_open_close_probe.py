"""Open-to-close intraday families on 10 years of daily bars, run EXACTLY as docs/INTRADAY_RESEARCH_PLAN.md says.

The gates are enforced here, not by discipline: validation (V) only runs for families that passed discovery (D),
confirmation (C, 5-minute archive, realistic fills) only for families that passed V.

Usage: .venv/bin/python -m scripts.intraday_open_close_probe
"""

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from app import data
from app.intraday import archive
from app.universe import BENCHMARK, STOCKS

COST = 0.0006                      # per side; plan: 0.12 % round trip per position
STRESS_COST = 0.0008
D_END, V_START, V_END = "2022-12-31", "2023-01-01", "2026-07-23"
QUANTILE, GAP_MIN, BAD_PRINT = 0.2, 0.01, 0.20
N_TESTS = 8
D_T = float(norm.isf(0.05 / N_TESTS))        # 2.50, Bonferroni one-sided
V_T, POSITIVE_SHARE, MIN_PERIOD_DAYS = 1.65, 0.60, 20


# ---------- panel: everything a pre-open decision may know, plus the open-to-close outcome ----------

def stock_frame(symbol: str, nifty_gap: pd.Series) -> pd.DataFrame | None:
    h = data.load_history(symbol)
    if h is None or len(h) < 30:
        return None
    h = h[h["Volume"] > 0]
    prev_close = h["Close"].shift()
    true_range = pd.concat([h["High"] - h["Low"], (h["High"] - prev_close).abs(), (h["Low"] - prev_close).abs()],
                           axis=1).max(axis=1)
    out = pd.DataFrame({
        "symbol": symbol,
        "gap": h["Open"] / prev_close - 1,
        "oc": h["Close"] / h["Open"] - 1,
        "prev_ret": prev_close / h["Close"].shift(2) - 1,
        "atr_prev": (true_range.rolling(14).mean() / h["Close"]).shift(),     # known at the previous close
    })
    out["rel_gap"] = out["gap"] - nifty_gap.reindex(out.index)
    return out


def build_panel() -> pd.DataFrame:
    nifty = data.load_history(BENCHMARK)
    nifty_gap = nifty["Open"] / nifty["Close"].shift() - 1
    frames = [f for s in STOCKS if (f := stock_frame(s, nifty_gap)) is not None]
    panel = pd.concat(frames).rename_axis("date").reset_index().dropna()
    return panel[(panel["gap"].abs() <= BAD_PRINT) & (panel["oc"].abs() <= BAD_PRINT)]


# ---------- the 4 families x 2 variants (signals use only pre-open information) ----------

def _rank_legs(df: pd.DataFrame, key: str, reverse: bool) -> pd.Series:
    """Per date: +1 long / -1 short for the bottom / top quintile of `key` (reverse=True: buy the bottom)."""
    by_date = df.groupby("date")[key]
    order, n = by_date.rank(method="first"), by_date.transform("size")
    k = (n * QUANTILE).astype(int).clip(lower=1)
    side = pd.Series(0, index=df.index)
    side[order <= k] = 1 if reverse else -1
    side[order > n - k] = -1 if reverse else 1
    return side


def positions(panel: pd.DataFrame, family: str, high_vol: bool) -> pd.DataFrame:
    df = panel
    if high_vol:
        df = df[df["atr_prev"] > df.groupby("date")["atr_prev"].transform("median")]
    if family == "F1 relative-gap reversal":
        side = _rank_legs(df, "rel_gap", reverse=True)
    elif family == "F4 one-day reversal":
        side = _rank_legs(df, "prev_ret", reverse=True)
    elif family == "F2 large-gap fade":
        side = -np.sign(df["gap"]).where(df["gap"].abs() >= GAP_MIN, 0)
    elif family == "F3 large-gap go":
        side = np.sign(df["gap"]).where(df["gap"].abs() >= GAP_MIN, 0)
    else:
        raise ValueError(family)
    out = df.assign(side=side)
    return out[out["side"] != 0]


FAMILIES = ("F1 relative-gap reversal", "F2 large-gap fade", "F3 large-gap go", "F4 one-day reversal")
TESTS = [(f, hv) for f in FAMILIES for hv in (False, True)]


# ---------- scoring ----------

def daily_pnl(pos: pd.DataFrame, cost: float = COST, ret_col: str = "oc") -> pd.Series:
    net = pos["side"] * pos[ret_col] - 2 * cost
    return net.groupby(pos["date"]).mean()


def stats(pos: pd.DataFrame, period: str, cost: float = COST, ret_col: str = "oc") -> dict:
    if pos.empty:
        return {"days": 0}
    daily = daily_pnl(pos, cost, ret_col)
    gross = daily_pnl(pos, 0.0, ret_col)
    t = daily.mean() / (daily.std(ddof=1) / math.sqrt(len(daily))) if len(daily) > 2 else float("nan")
    key = daily.index.year.astype(str) if period == "year" else \
        daily.index.year.astype(str) + "-H" + ((daily.index.month > 6) + 1).astype(str)
    by = daily.groupby(key).agg(["mean", "size"])
    by = by[by["size"] >= MIN_PERIOD_DAYS]
    return {"days": len(daily), "positions": len(pos), "per_day": len(pos) / len(daily), "net": daily.mean(),
            "gross": gross.mean(), "t": t, "positive_share": float((by["mean"] > 0).mean()) if len(by) else float("nan"),
            "periods": len(by), "win": float((pos["side"] * pos[ret_col] - 2 * cost > 0).mean())}


def passes_d(s: dict) -> bool:
    return s["days"] > 0 and s["net"] > 0 and s["t"] >= D_T and s["positive_share"] >= POSITIVE_SHARE


def passes_v(s: dict, stressed: dict) -> bool:
    return s["days"] > 0 and s["net"] > 0 and s["t"] >= V_T and s["positive_share"] >= POSITIVE_SHARE \
        and stressed["net"] > 0


def line(label: str, s: dict, verdict: str) -> str:
    if not s.get("days"):
        return f"  {label:38} no trades"
    return (f"  {label:38}{s['days']:>6}{s['per_day']:>6.1f}{s['gross']:>+9.3%}{s['net']:>+9.3%}{s['win']:>6.0%}"
            f"{s['t']:>7.2f}{s['positive_share']:>7.0%}  {verdict}")


HEADER = f"  {'test':38}{'days':>6}{'pos/d':>6}{'gross':>9}{'net':>9}{'win':>6}{'t':>7}{'per+':>7}"


# ---------- confirmation on the 5-minute archive (realistic fills) ----------

def confirmation_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Add oc_0915 (09:15 bar open -> 15:10 bar close) and oc_0920 (late fill) from the 5-minute archive."""
    rows = []
    for symbol in panel["symbol"].unique():
        raw = archive.load(symbol)
        if raw is None:
            continue
        for day, bars in raw.groupby(raw.index.date):
            t = bars.index.strftime("%H:%M")
            first, late, last = bars[t == "09:15"], bars[t == "09:20"], bars[t == "15:10"]
            if len(first) and len(late) and len(last):
                exit_price = float(last["Close"].iloc[0])
                rows.append({"date": pd.Timestamp(day), "symbol": symbol,
                             "oc_0915": exit_price / float(first["Open"].iloc[0]) - 1,
                             "oc_0920": exit_price / float(late["Open"].iloc[0]) - 1})
    fills = pd.DataFrame(rows)
    return panel.merge(fills, on=["date", "symbol"], how="inner") if len(fills) else panel.iloc[0:0]


def main() -> None:
    panel = build_panel()
    disc = panel[panel["date"] <= D_END]
    valid = panel[(panel["date"] >= V_START) & (panel["date"] <= V_END)]
    print(f"panel {len(panel):,} stock-days, {panel['symbol'].nunique()} stocks, "
          f"{panel['date'].min():%Y-%m-%d} to {panel['date'].max():%Y-%m-%d}")
    print(f"\nD: discovery {disc['date'].min():%Y-%m-%d} to {D_END}  (pass: net > 0, t >= {D_T:.2f}, "
          f">= {POSITIVE_SHARE:.0%} of years positive)\n{HEADER}")
    survivors = []
    for family, hv in TESTS:
        label = f"{family}{' / high-vol' if hv else ''}"
        s = stats(positions(disc, family, hv), "year")
        ok = passes_d(s)
        survivors += [(family, hv, label)] if ok else []
        print(line(label, s, "PASS" if ok else "fail"))

    if not survivors:
        print("\nNo family passed discovery: validation and confirmation stay closed (as pre-registered).")
        return
    print(f"\nV: validation {V_START} to {V_END}, survivors only (pass: net > 0, t >= {V_T}, "
          f">= {POSITIVE_SHARE:.0%} of half-years positive, net > 0 at {STRESS_COST:.2%}/side)\n{HEADER}")
    finalists = []
    for family, hv, label in survivors:
        pos = positions(valid, family, hv)
        s, stressed = stats(pos, "half"), stats(pos, "half", STRESS_COST)
        ok = passes_v(s, stressed)
        finalists += [(family, hv, label)] if ok else []
        print(line(label, s, f"{'PASS' if ok else 'fail'} (net at {STRESS_COST:.2%}/side {stressed['net']:+.3%})"))

    if not finalists:
        print("\nNo family passed validation: confirmation stays closed (as pre-registered).")
        return
    conf = confirmation_returns(panel[panel["date"] > V_END])
    print(f"\nC: confirmation on the 5-minute archive, {conf['date'].min():%Y-%m-%d} to {conf['date'].max():%Y-%m-%d} "
          f"(pass: net > 0 at 09:15 fill, t > -1 at 09:20 fill)\n{HEADER}")
    for family, hv, label in finalists:
        pos = positions(conf, family, hv)
        on_time, late = stats(pos, "half", ret_col="oc_0915"), stats(pos, "half", ret_col="oc_0920")
        ok = on_time.get("days") and on_time["net"] > 0 and late["t"] > -1
        print(line(f"{label} @09:15", on_time, "PASS" if ok else "fail"))
        print(line(f"{label} @09:20", late, ""))


if __name__ == "__main__":
    main()
