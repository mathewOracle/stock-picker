"""Intraday trade arithmetic: cost in R and the break-even win rate."""

import math

import pytest

from app.intraday import economics
from app.tradeplan import TradePlan


def plan(entry=100.0, stop=99.0, target=102.0) -> TradePlan:
    return TradePlan(entry, stop, target, target + (entry - stop), "test")


def test_cost_is_a_bigger_share_of_a_tighter_stop():
    wide, tight = plan(stop=99.0), plan(stop=99.8)
    assert economics.cost_r(tight) > economics.cost_r(wide)
    assert economics.cost_r(wide) == pytest.approx(2 * economics.COST_PER_SIDE / 0.01)


def test_break_even_matches_the_expected_value_formula():
    p = plan(stop=99.0, target=102.0)                      # RR 2, risk 1%
    need = economics.break_even_win_rate(p)
    cost = economics.cost_r(p)
    assert need * p.reward_risk - (1 - need) - cost == pytest.approx(0, abs=1e-12)
    assert need > 1 / 3                                    # costs push it above the cost-free 33%


def test_short_plans_use_the_same_arithmetic():
    long_, short = plan(), TradePlan(100.0, 101.0, 98.0, 97.0, "test")
    assert economics.break_even_win_rate(short) == pytest.approx(economics.break_even_win_rate(long_))


def test_degenerate_plans_never_look_free():
    assert economics.cost_r(plan(stop=100.0)) == math.inf
    assert economics.break_even_win_rate(plan(stop=100.0)) == 1.0


def test_trade_math_compares_backtest_winners_to_the_bar():
    p = plan()
    need = economics.break_even_win_rate(p)
    above = economics.trade_math(p, {"n": 300, "win_rate": need + 0.05})
    below = economics.trade_math(p, {"n": 300, "win_rate": need - 0.05})
    assert above["clears"] and not below["clears"]
    none = economics.trade_math(p, {"status": "not backtested", "n": 0})
    assert none["won"] is None and none["clears"] is False
    assert "backtest won" not in economics.describe(none) and "backtest won" in economics.describe(above)
