"""Intraday trade arithmetic: what the round-trip cost does to a plan, and the win rate it needs to break even.

Pure arithmetic, nothing fitted, so it needs no backtest to be true. Why it is shown on every plan: the research in
docs/INTRADAY_RESEARCH_PLAN.md found every setup tested so far has about zero edge BEFORE costs, so costs decide
the outcome. Single source of truth for the cost assumption (the backtest imports it from here).
"""

import math

from app.tradeplan import TradePlan

COST_PER_SIDE = 0.0006     # brokerage + STT + exchange fees + GST + stamp + slippage, NSE intraday, large caps


def cost_r(plan: TradePlan) -> float:
    """Round-trip cost as a share of the plan's risk (entry to stop)."""
    return 2 * COST_PER_SIDE / plan.risk_pct if plan.risk_pct > 0 else math.inf


def break_even_win_rate(plan: TradePlan) -> float:
    """Expected value p*RR - (1-p) - cost_R = 0  ->  p = (1 + cost_R) / (RR + 1), RR to target 1."""
    if plan.risk_pct <= 0 or plan.reward_risk <= 0:     # no risk to measure against, or no reward: never 'free'
        return 1.0
    return min(1.0, (1 + cost_r(plan)) / (plan.reward_risk + 1))


def trade_math(plan: TradePlan, evidence: dict) -> dict:
    """The plan's break-even bar next to how often this playbook+side actually ended in profit in the backtest."""
    won = evidence.get("win_rate") if evidence.get("n") else None
    need = break_even_win_rate(plan)
    return {"cost_r": cost_r(plan), "break_even": need, "won": won, "n": evidence.get("n", 0),
            "clears": won is not None and won >= need}


def describe(math_: dict) -> str:
    text = f"needs {math_['break_even']:.0%} winners to break even after costs (costs = {math_['cost_r']:.2f}R)"
    if math_["won"] is not None:
        text += f"; backtest won {math_['won']:.0%} of {math_['n']} trades"
    return text
