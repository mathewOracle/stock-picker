"""The information-only model view: calibration evidence, driver explanations, and its safety rules."""

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app import analysis
from app.research import meta, model_view

COLUMNS = ["reward_risk", "rsi"]


def oos_frame(n=4000, seed=0, informative=True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.2, 0.7, n)
    won = rng.random(n) < (p if informative else 0.45)
    return pd.DataFrame({"p": p, "label": won.astype(int), "o_net_return": np.where(won, 0.03, -0.02),
                         "date": pd.date_range("2020-01-01", periods=n, freq="D")})


def test_calibration_bins_track_reality_and_reuse_selection_edges():
    selection, holdout = oos_frame(seed=0), oos_frame(seed=1)
    edges = meta.calibration_edges(selection)
    assert edges[0] == 0.0 and edges[-1] == 1.0 and len(edges) == meta.CALIBRATION_BINS + 1
    cal = meta.calibration(selection, edges)
    rates = [b["win_rate"] for b in cal["bins"]]
    assert rates == sorted(rates) and cal["auc"] > 0.55            # a score that means something
    assert sum(b["n"] for b in cal["bins"]) == cal["n"] == len(selection)
    held = meta.calibration(holdout, edges)                          # same bands, different data
    assert [b["lo"] for b in held["bins"]] == [b["lo"] for b in cal["bins"]]


def test_calibration_exposes_a_score_that_tells_nothing():
    cal = meta.calibration(oos_frame(informative=False), meta.calibration_edges(oos_frame(informative=False)))
    rates = [b["win_rate"] for b in cal["bins"]]
    assert max(rates) - min(rates) < 0.08 and abs(cal["auc"] - 0.5) < 0.05


def test_similar_finds_the_band_including_the_top_edge():
    cal = {"bins": [{"lo": 0.0, "hi": 0.4}, {"lo": 0.4, "hi": 1.0}]}
    assert model_view.similar(cal, 0.39)["lo"] == 0.0
    assert model_view.similar(cal, 0.40)["lo"] == 0.4 and model_view.similar(cal, 1.0)["lo"] == 0.4
    assert model_view.similar(None, 0.5) is None


def bundle_and_report():
    rng = np.random.default_rng(0)
    x = pd.DataFrame({"reward_risk": rng.normal(2, 1, 2000), "rsi": rng.normal(50, 10, 2000)})
    y = (x["reward_risk"] + rng.normal(0, 1, 2000) > 2).astype(int)        # reward/risk helps, rsi is noise
    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression()).fit(x, y)
    cal = meta.calibration(oos_frame(), meta.calibration_edges(oos_frame()))
    report = {"target": "trade_win", "best": "logistic", "adopted": False, "why": "Not adopted.", "columns": COLUMNS,
              "period": ["2017-01-01", "2026-01-01"], "calibration": {"selection": cal, "holdout": cal}}
    return {"model": model, "columns": COLUMNS, "cut": 0.45}, report


def test_view_explains_the_score_with_drivers_and_evidence():
    bundle, report = bundle_and_report()
    v = model_view.view(bundle, report, {"reward_risk": 4.0, "rsi": 50.0, "unused": 1.0})
    assert 0.5 < v["p"] < 1 and v["adopted"] is False and v["cut"] == 0.45
    assert v["up"][0]["feature"] == "reward_risk" and v["up"][0]["label"] == "Reward/risk of the plan"
    assert v["similar_selection"]["lo"] <= v["p"] or v["similar_selection"]["hi"] >= 1.0
    low = model_view.view(bundle, report, {"reward_risk": 0.0, "rsi": 50.0})
    assert low["p"] < v["p"] and low["down"][0]["feature"] == "reward_risk"


def test_view_is_absent_rather_than_wrong():
    bundle, report = bundle_and_report()
    assert model_view.view(None, report, {"reward_risk": 1}) is None
    assert model_view.view(bundle, report, None) is None
    assert model_view.view(bundle, report, {"oops": 1}) is None                  # scoring error -> no view


def test_load_refuses_a_model_file_from_a_different_run(monkeypatch):
    bundle, report = bundle_and_report()
    monkeypatch.setattr(model_view.data, "load_result", lambda key: {**report, "columns": ["something_else"]})
    monkeypatch.setattr(model_view.ml, "load_model", lambda path: bundle)
    assert model_view.load()[0] is None
    monkeypatch.setattr(model_view.data, "load_result", lambda key: report)
    assert model_view.load()[0] is bundle


def test_the_info_view_never_becomes_the_adopted_gate_score():
    """metrics['ml_prob'] means 'adopted gate score' (the intraday ML column reads it): no adopted model, no key."""
    metrics = {}
    assert analysis._ml_gate(None, {"reward_risk": 2.0}, metrics) is None and "ml_prob" not in metrics
