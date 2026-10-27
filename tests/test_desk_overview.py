"""The order desk overview (status tiles + "needs attention"): pure functions over the list rows."""

from types import SimpleNamespace as NS

from app import deskview

FRESH = {"label": "5 min ago", "stale": False, "why": ""}
STALE = {"label": "3 days ago", "stale": True, "why": "Daily prices are 3 days old"}


def swing(symbol, verdict, candidate=False):
    return {"r": NS(symbol=symbol, name=symbol.title(), verdict=verdict), "candidate": candidate}


def intraday(symbol, kind, lean="flat", setups=(), verdict="No trade", reason=""):
    return {"r": NS(symbol=symbol, name=symbol.title(), verdict=verdict, reason=reason, setups=list(setups)),
            "kind": kind, "lean": lean}


def test_swing_tally_groups_verdicts():
    rows = [swing("A", "Strong Buy"), swing("B", "Buy"), swing("C", "Watchlist", candidate=True),
            swing("D", "Hold"), swing("E", "Avoid"), swing("F", "Avoid")]
    assert deskview.tally(rows, "swing") == {"buy": 2, "watch": 1, "hold": 1, "avoid": 2, "candidate": 1, "total": 6}


def test_intraday_tally_separates_unvalidated_from_near_misses():
    """The bug the screenshot caught: 'found, but reward/risk below 1.5' is a near-miss, not 'nothing'."""
    rows = [intraday("A", "setup", "long", setups=["orb"]),
            intraday("B", "candidate", "long", setups=["vwap"]),          # passes checks, playbook not validated
            intraday("C", "none", "long", setups=["vwap"]),               # pattern found, a check failed
            intraday("D", "none", "short"), intraday("E", "wait")]
    t = deskview.tally(rows, "intraday")
    assert (t["setup"], t["candidate"], t["near_miss"], t["quiet"]) == (1, 1, 1, 2)
    assert (t["long"], t["short"], t["flat"], t["total"]) == (3, 1, 1, 5)


def test_attention_orders_problems_then_actionable_then_cautions():
    rows = [swing("A", "Watchlist", candidate=True), swing("B", "Buy"), swing("C", "Hold")]
    items, total = deskview.attention("swing", rows, STALE)
    assert total == 3
    assert [(i["status"], i["symbol"]) for i in items] == [("crit", ""), ("ok", "B"), ("warn", "A")]
    assert "refresh before ordering" in items[0]["reason"]


def test_attention_intraday_lists_setups_and_unvalidated_only():
    rows = [intraday("A", "candidate", reason="Not validated"), intraday("B", "setup", verdict="Long setup"),
            intraday("C", "none", setups=["vwap"]), intraday("D", "wait")]
    items, total = deskview.attention("intraday", rows, FRESH)
    assert total == 2 and [(i["status"], i["symbol"], i["reason"]) for i in items] == \
        [("ok", "B", "Long setup"), ("warn", "A", "Not validated")]


def test_attention_is_capped_but_counts_everything():
    rows = [swing(f"S{n}", "Watchlist", candidate=True) for n in range(deskview.ATTENTION_LIMIT + 5)]
    items, total = deskview.attention("swing", rows, FRESH)
    assert len(items) == deskview.ATTENTION_LIMIT and total == deskview.ATTENTION_LIMIT + 5


def test_nothing_to_flag_is_an_empty_strip():
    assert deskview.attention("swing", [swing("A", "Hold")], FRESH) == ([], 0)
