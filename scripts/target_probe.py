"""Does training on the requirement's own question fix the meta-model? (research probe)

Finding that motivated this (visible in the WALK-FORWARD calibration alone, before any hold-out look): the
production model ranks P(trade ends in profit) well (win rate rises with score) but the high-score band earns
LESS than the low-score band. It learned 'safe small winners', while adoption measures EDGE over random entry.

Probe: same models, same protocol, but label = "beat the median trade of all stocks on the same date"
(cross-sectional), which is exactly what the adoption edge measures and strips out market direction.

Pre-registered rule: the hold-out is only opened if the walk-forward (selection) period ALREADY clears the
production bar (filtered t >= MIN_T, >= FOLDS_POSITIVE folds positive, beats the rule). The hold-out has been
viewed before, so even a pass here would need forward (paper) confirmation before adoption.

Usage: .venv/bin/python -m scripts.target_probe
"""

import numpy as np

from app.research import ledger, meta


def relabel(df):
    out = df.copy()
    out["label"] = (out["o_net_return"] > out.groupby("date")["o_net_return"].transform("median")).astype(int)
    return out


def clears_bar(result: dict) -> bool:
    f, rule = result.get("filtered", {}), result.get("rule", {})
    return bool(f.get("n") and np.nan_to_num(f.get("t_stat"), nan=-9) >= meta.MIN_T
                and result.get("folds_positive", 0) >= meta.FOLDS_POSITIVE
                and f.get("avg_return", -9) > rule.get("avg_return", 9))


def line(label: str, result: dict) -> str:
    f = result.get("filtered", {})
    return (f"  {label:36}{f.get('n', 0):>6}{f.get('avg_return', np.nan):>+9.2%}{f.get('edge', np.nan):>+8.2%}"
            f"{f.get('t_stat', np.nan):>7.2f}{result.get('folds_positive', np.nan):>8.0%}  "
            f"{'clears bar' if clears_bar(result) else 'fails bar'}")


def main() -> None:
    raw, _ = ledger.load()
    base = meta.prepare(raw)
    folds = meta.folds_for(base)
    selection = [f for f in folds if f[1] < meta.HOLDOUT_START]
    holdout = [f for f in folds if f[1] >= meta.HOLDOUT_START]
    print(f"  {'':36}{'trades':>6}{'avg':>9}{'edge':>8}{'t':>7}{'folds+':>8}")
    rule = meta.score_filter(meta.oos_scores(base, meta.candidates()["logistic"], selection))
    print(line("selection: unfiltered rule", {**rule, "filtered": rule["rule"]}))

    results = {}
    for target, df in (("profit (production)", base), ("beat same-day median", relabel(base))):
        for name, factory in meta.candidates().items():
            results[(target, name)] = meta.score_filter(meta.oos_scores(df, factory, selection))
            print(line(f"selection: {name} / {target}", results[(target, name)]))

    passing = [k for k in results if k[0] != "profit (production)" and clears_bar(results[k])]
    if not passing:
        print("\nNo relabelled model clears the bar on the walk-forward period -> hold-out stays closed.")
        return
    target, name = max(passing, key=lambda k: results[k]["filtered"]["t_stat"])
    df = relabel(base)
    print(line(f"HOLD-OUT: {name} / {target}", meta.score_filter(meta.oos_scores(df, meta.candidates()[name], holdout))))
    print(line(f"HOLD-OUT unseen stocks: {name}", meta.score_filter(
        meta.oos_scores(df, meta.candidates()[name], holdout, symbol_holdout=True))))


if __name__ == "__main__":
    main()
