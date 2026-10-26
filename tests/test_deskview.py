"""The desk's ranking and filtering rules: buy intensity, short intensity, candidates, selection fallback."""

from types import SimpleNamespace

from app import deskview
from app.research.signal_record import SIGNAL_COLUMNS
from app.signals import Signal


def swing(symbol, composite, verdict="Hold", rule="Hold"):
    return SimpleNamespace(symbol=symbol, scores={"composite": composite}, verdict=verdict, rule_verdict=rule,
                           metrics={"sector": "Tech"})


def live(symbol, bias, verdict="No trade"):
    return SimpleNamespace(symbol=symbol, scores={"bias": bias}, verdict=verdict,
                           technical=[Signal("RSI (5m)", "55", 0.5, 1.0, "n")], context=[Signal("Liquidity", "ok", 0.2, 1.0, "n")])


def test_swing_is_ranked_by_composite_best_first_and_flags_unvalidated_candidates():
    result = SimpleNamespace(reports=[swing("A", 40), swing("B", 71, "Watchlist", "Buy"), swing("C", 58, "Buy", "Buy")])
    rows = deskview.swing_rows(result)
    assert [row["r"].symbol for row in rows] == ["B", "C", "A"]
    assert [row["candidate"] for row in rows] == [True, False, False]     # C is a validated Buy, not a "candidate"


def test_intraday_buy_and_short_intensity_rank_in_opposite_directions():
    scan = SimpleNamespace(reports=[live("A", 62), live("B", 30), live("C", 50)])
    assert [r["r"].symbol for r in deskview.intraday_rows(scan, "long")] == ["A", "C", "B"]
    assert [r["r"].symbol for r in deskview.intraday_rows(scan, "short")] == ["B", "C", "A"]


def test_short_intensity_is_the_mirror_of_buy_intensity():
    row = deskview.intraday_rows(SimpleNamespace(reports=[live("A", 62)]))[0]
    assert (row["buy"], row["short"]) == (62, 38)


def test_intraday_rows_are_tagged_for_the_filters():
    scan = SimpleNamespace(reports=[live("A", 70, "Long setup"), live("B", 40, "Short candidate"), live("C", 50, "Wait"),
                                    live("D", 50)])
    tags = {row["r"].symbol: (row["kind"], row["lean"]) for row in deskview.intraday_rows(scan)}
    assert tags == {"A": ("setup", "long"), "B": ("candidate", "short"), "C": ("wait", "flat"), "D": ("none", "flat")}


def test_lean_uses_the_live_bias_thresholds():
    assert deskview.lean(55) == "long" and deskview.lean(45) == "short" and deskview.lean(54.9) == "flat"


def test_selection_falls_back_to_the_top_stock_and_survives_an_empty_tab():
    rows = deskview.swing_rows(SimpleNamespace(reports=[swing("A", 40), swing("B", 70)]))
    assert deskview.pick(rows, "A").symbol == "A"
    assert deskview.pick(rows, "MISSING.NS").symbol == "B"       # a symbol from the other tab must not break this one
    assert deskview.pick(rows, "").symbol == "B"
    assert deskview.pick([], "A") is None


def test_intraday_signals_get_their_two_pillars_and_an_honest_evidence_note():
    rows = deskview.signal_rows(live("A", 60), "intraday")
    assert [(r["pillar"], r["record"]) for r in rows] == [("Technical", None), ("Context", None)]
    assert "backtested as a whole" in rows[0]["evidence"]


NOW = 1_800_000_000.0


def test_freshness_swing_tolerates_a_long_weekend_but_not_a_week():
    assert not deskview.freshness(NOW - 3 * 86_400, "swing", False, NOW)["stale"]
    old = deskview.freshness(NOW - 5 * 86_400, "swing", False, NOW)
    assert old["stale"] and old["label"] == "5 days ago" and "5 days old" in old["why"]


def test_freshness_intraday_only_ages_while_the_market_is_open():
    assert deskview.freshness(NOW - 20 * 60, "intraday", True, NOW)["stale"]
    assert not deskview.freshness(NOW - 20 * 60, "intraday", False, NOW)["stale"]     # after the close the last bars ARE the latest
    assert deskview.freshness(NOW - 30, "intraday", True, NOW) == {"label": "just now", "stale": False, "why": ""}


def test_never_fetched_data_is_always_stale():
    assert deskview.freshness(None, "swing", False, NOW)["stale"]


def test_evidence_counts_ignore_signals_without_enough_history():
    rows = [{"record": {"status": "edge"}}, {"record": {"status": "none"}}, {"record": {"status": "insufficient"}},
            {"record": None}]
    assert deskview.evidence_counts(rows) == (1, 2)
    assert "RSI (14)" in SIGNAL_COLUMNS                            # the names the swing rows are matched on
