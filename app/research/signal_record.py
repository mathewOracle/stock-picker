"""Per-signal track record: does a price signal's score rank the 20-day forward return, week by week?

Read straight from the backtest ledger (26k weekly evaluations), so the Desk can show the evidence next to
every reading. The method is deliberately the sceptical one: weekly evaluations overlap (the horizon is
20 sessions), so the t-statistic uses every 4th week, and the bar is Bonferroni-corrected for the number
of signals tested.
"""

from statistics import NormalDist

import numpy as np
import pandas as pd

from app.research import ledger
from app.research.features import CHART_SIGNALS, TECHNICAL_SIGNALS, slug

THIN_WEEKS = 4      # overlap guard: forward returns span ~4 weekly evaluations
ALPHA = 0.05
MIN_WEEKS = 20      # fewer independent weeks than this proves nothing

SIGNAL_COLUMNS = {**{name: f"t_{slug(name)}" for name in TECHNICAL_SIGNALS},
                  **{name: f"c_{slug(name)}" for name in CHART_SIGNALS}}


def bar() -> float:
    """|t| a signal must beat after correcting for testing every signal at once (two-sided)."""
    return NormalDist().inv_cdf(1 - ALPHA / (2 * len(SIGNAL_COLUMNS)))


def weekly_ic(frame: pd.DataFrame, column: str) -> pd.Series:
    """Spearman correlation of the signal's points with the forward return, one value per evaluation week."""
    def one_week(group: pd.DataFrame) -> float:
        return group[column].corr(group["fwd"], method="spearman") if group[column].nunique() > 1 else np.nan
    return frame.groupby("date")[[column, "fwd"]].apply(one_week).dropna()


def judge(ic: pd.Series) -> dict:
    thin = ic.iloc[::THIN_WEEKS]
    if len(thin) < MIN_WEEKS or not thin.std():
        return {"status": "insufficient", "ic": float("nan"), "t": float("nan"), "weeks": len(thin)}
    t = float(thin.mean() / thin.std() * np.sqrt(len(thin)))
    status = "edge" if t >= bar() else "wrong way" if t <= -bar() else "none"
    return {"status": status, "ic": float(ic.mean()), "t": t, "weeks": len(thin)}


def compute(frame: pd.DataFrame) -> dict[str, dict]:
    frame = frame.dropna(subset=["fwd"])
    return {name: judge(weekly_ic(frame, column)) for name, column in SIGNAL_COLUMNS.items()
            if column in frame.columns}


_memo: tuple[float, dict[str, dict]] | None = None


def records() -> dict[str, dict]:
    """Signal name -> {status, ic, t, weeks}. Empty when there is no ledger yet. Recomputed only when it changes."""
    global _memo
    if not ledger.LEDGER_PATH.exists():
        return {}
    stamp = ledger.LEDGER_PATH.stat().st_mtime
    if _memo is None or _memo[0] != stamp:
        frame, _ = ledger.load()
        _memo = (stamp, compute(frame) if frame is not None else {})
    return _memo[1]


def describe(record: dict | None) -> str:
    """One plain-English line for the UI."""
    if not record:
        return "Not backtested (fundamental signals have no price history; Yahoo keeps 4-5 years of statements)."
    if record["status"] == "insufficient":
        return "Too few weeks of history to judge."
    base = f"Rank correlation with the next 20 days' return {record['ic']:+.3f} (t {record['t']:+.2f} over {record['weeks']} weeks)"
    return {
        "edge": f"{base}: passes the corrected bar (|t| >= {bar():.2f}).",
        "wrong way": f"{base}: significantly the WRONG way round.",
        "none": f"{base}: no proven edge (bar is |t| >= {bar():.2f}).",
    }[record["status"]]
