"""Price-only stock rankings vs the universe average (docs/SWING_RESEARCH_PLAN.md).

Shared by the frozen research probe (scripts/swing_factor_probe.py) and the forward test (forward.py), so both
score portfolios with literally the same code.
"""

import math
from collections.abc import Callable

import numpy as np
import pandas as pd

from app.research.backtest import COST_PER_SIDE

STEP = 20                    # sessions between rebalances = holding period
WARMUP = 253                 # 252-session lookback plus the signal bar
QUANTILE, MIN_NAMES = 0.2, 30
MIN_T, POSITIVE_SHARE, MIN_YEAR_PERIODS = 1.65, 0.60, 4

# family -> (feature column, higher_is_better)
FAMILIES = {
    "M1 12-1 momentum": ("mom_12_1", True),
    "M2 6-1 momentum": ("mom_6_1", True),
    "M3 52-week-high proximity": ("hi52", True),
    "M4 low volatility": ("vol60", False),
    "M5 one-month reversal": ("ret_1m", False),
    "M6 risk-adjusted momentum": ("rar", True),
}


def features(close: pd.Series) -> pd.DataFrame:
    """Everything known at each day's close (no future data)."""
    daily = np.log(close).diff()
    mom_6_1 = close.shift(21) / close.shift(126) - 1
    vol60 = daily.rolling(60).std()
    return pd.DataFrame({
        "mom_12_1": close.shift(21) / close.shift(252) - 1, "mom_6_1": mom_6_1,
        "hi52": close / close.rolling(252).max(), "vol60": vol60,
        "ret_1m": close / close.shift(21) - 1, "rar": mom_6_1 / vol60})


def top_quintile(group: pd.DataFrame, family: str) -> pd.DataFrame:
    """The best-ranked fifth of one rebalance's eligible stocks (at least one)."""
    col, high_good = FAMILIES[family]
    k = max(1, int(len(group) * QUANTILE))
    return group.nlargest(k, col) if high_good else group.nsmallest(k, col)


Picker = Callable[[pd.DataFrame, str], pd.DataFrame]


def portfolio(panel: pd.DataFrame, family: str, overlay: bool = False, cost_mult: float = 1.0,
              pick: Picker = top_quintile) -> pd.DataFrame:
    """Per-rebalance gross/net results of the picks vs the universe average.

    `panel` has one row per (rebalance `n`, stock) with `signal`, `symbol` and realised `ret`. `pick` chooses the
    portfolio from each rebalance: ranked here by default, or the recorded picks in the forward test.
    """
    out, previous = [], set()
    for _, group in panel.groupby("n"):
        if len(group) < MIN_NAMES:
            continue
        picks = pick(group, family)
        if picks.empty:            # forward test only: every recorded pick lost its prices
            continue
        names = set(picks["symbol"])
        entered = len(names - previous) / len(names)
        previous = names
        in_market = (not overlay) or bool(group["nifty_above_200"].iloc[0])
        gross_top = picks["ret"].mean() if in_market else 0.0
        out.append({"signal": group["signal"].iloc[0], "top": gross_top, "universe": group["ret"].mean(),
                    "cost": COST_PER_SIDE * 2 * entered * cost_mult * (1 if in_market else 0), "entered": entered})
    res = pd.DataFrame(out)
    if res.empty:
        return res
    res["excess_gross"] = res["top"] - res["universe"]
    res["excess_net"] = res["excess_gross"] - res["cost"]
    res["net_top"] = res["top"] - res["cost"]
    return res


def stats(res: pd.DataFrame) -> dict:
    if len(res) < 3:
        return {"periods": len(res)}
    x = res["excess_net"]
    years = res.groupby(res["signal"].dt.year)["excess_net"].agg(["mean", "size"])
    years = years[years["size"] >= MIN_YEAR_PERIODS]
    return {"periods": len(res), "gross": res["excess_gross"].mean(), "net": x.mean(),
            "t": x.mean() / (x.std(ddof=1) / math.sqrt(len(x))), "years": len(years),
            "pos": float((years["mean"] > 0).mean()) if len(years) else float("nan"),
            "top": res["top"].mean(), "universe": res["universe"].mean(), "turnover": res["entered"].mean()}


def passes(s: dict, min_t: float, need_years: bool = True) -> bool:
    ok = s.get("periods", 0) >= 3 and s["net"] > 0 and s["t"] >= min_t
    return ok and (not need_years or (s["pos"] >= POSITIVE_SHARE))
