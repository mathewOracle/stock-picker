# Swing research plan (pre-registered)

Written and committed **before** any test below was run. A threshold, period or family changed after seeing
results makes the result worthless; new ideas get a new dated plan.

## Measured before this plan (descriptive; nothing was selected from it)

On the existing 26,362-row weekly ledger (63 stocks, 2017-11 to 2026-09), over a plain 20-session hold from the
next open (no stops or targets):

| Period | Rule signals | Rule 20d | All stocks 20d | Excess | t (independent windows) |
|---|---|---|---|---|---|
| all | 5,724 | +1.06 % | +1.35 % | -0.28 % | -1.53 |
| 2017-21 | 2,616 | +1.24 % | +1.58 % | -0.35 % | -1.01 |
| 2022-24 | 2,137 | +1.52 % | +1.79 % | -0.26 % | -0.63 |
| 2024-11 on | 971 | 0.00 % | +0.18 % | -0.18 % | +0.84 |

* The rule's **entries** have no skill (slightly negative, every period). The stop/target plan is not the
  cause: +1.06 % of raw 20-day return becomes +0.33 % net per trade, of which cost is 0.30 %.
* The hurdle is "equal-weight buy-and-hold of the universe": +1.35 % per 20 sessions. Part is a bull market,
  part is **survivorship bias** (the universe is today's large caps replayed over 10 years): every result
  below is flattered, so a failure here is a strong "no" and a pass is a weaker "yes".
* Fundamentals (40 % of the composite) cannot be backtested: only today's snapshot is stored, so using it
  in the past would be lookahead. That pillar is untested, and is reported as untested.

## Question

Instead of tuning the existing composite, do **simple, published, price-only stock rankings** pick better
stocks than the universe average, after realistic costs, in three independent periods?

## Design

* Rebalance every 20 sessions (non-overlapping). Signal at the close of day d, buy at the open of d+1, sell at
  the close of d+20. Adjusted prices. A stock needs the full history for its factor and prices for both ends.
  A rebalance needs >= 30 eligible stocks.
* Portfolio = **top quintile** (long-only: Indian cash-market investors cannot hold short positions overnight),
  equal weight. Benchmark = equal-weight average of every eligible stock over the same window.
* Cost: 0.15 % per side (0.30 % round trip, same as the existing backtest), charged on **new entries only**
  (a name held over from the previous period is not sold and rebought). The benchmark pays nothing.
* Net excess per period = mean(top quintile) - mean(universe) - cost.
* t-statistic over periods (one observation per rebalance, so no overlap). "Years positive" counts calendar
  years with >= 4 periods.

## Periods (each opened once, only by what survived the previous one)

| Stage | Signal dates | Pass rule |
|---|---|---|
| D discovery | 2017-11 to 2021-12 | net excess > 0, t >= 1.65, >= 60 % of years positive |
| V validation | 2022-01 to 2024-10 | net excess > 0, t >= 1.65, >= 60 % of years positive, still > 0 at double cost |
| C confirmation | 2024-11 to latest | net excess > 0 and t >= 1.0 (short sample) |

Independent sequential gates control false positives: a family with no true edge passes D, V and C with
probability about 0.05 x 0.05 x 0.16 = 0.0004 (x 6 families = 0.0024). The C period was seen before when
judging the old rule and the ML model, but never for these rankings.

## Six families (each is a published effect with an a-priori reason)

1. **M1 12-1 momentum**: return from t-252 to t-21 (skip the latest month), highest.
2. **M2 6-1 momentum**: return from t-126 to t-21, highest.
3. **M3 52-week-high proximity**: close / highest close of the last 252 sessions, highest (anchoring).
4. **M4 low volatility**: 60-session daily-return standard deviation, lowest.
5. **M5 one-month reversal**: 21-session return, lowest (buy last month's losers; liquidity effect).
6. **M6 risk-adjusted momentum**: M2 return divided by the 60-session volatility, highest.

No other variants (no other lookbacks, quantiles or holding periods) are run.

## Descriptive only, never used to pick (finalists only)

* **Market-regime overlay**: hold cash when Nifty is below its 200-DMA at the signal date. Reports the
  average period return and the worst peak-to-trough fall of each net-of-cost series.
* Number of names, turnover and how often each year's top quintile outperformed.

## What each outcome means for the app

* A family that passes D, V and C becomes a **candidate ranking shown beside the existing verdict** (information
  first), with its evidence on /research, until it has also been checked going forward.
* If none passes, the honest conclusion is: with this universe and data, **no simple swing edge over holding
  the basket is established**, and the Buy list stays labelled unvalidated.

---

# Results of the main plan (run once, 2026-10-23, commit 60dba8e)

D (2017-11 to 2021-12, 52 rebalances): **no family passed**, so V and C stayed closed.

| Family | Top quintile | Universe | Gross excess | Net excess | t | Years + |
|---|---|---|---|---|---|---|
| M1 12-1 momentum | +1.58 % | +1.83 % | -0.25 % | -0.32 % | -0.91 | 25 % |
| M2 6-1 momentum | +1.78 % | +1.83 % | -0.05 % | -0.16 % | -0.35 | 50 % |
| M3 52-week-high proximity | +1.92 % | +1.83 % | +0.09 % | -0.06 % | -0.13 | 25 % |
| M4 low volatility | +1.49 % | +1.83 % | -0.33 % | -0.43 % | -0.97 | 25 % |
| M5 one-month reversal | +2.10 % | +1.83 % | +0.27 % | +0.02 % | 0.05 | 75 % |
| M6 risk-adjusted momentum | +1.46 % | +1.83 % | -0.37 % | -0.49 % | -1.08 | 25 % |

**Power (descriptive, computed after the run, used to design Addendum A only):** a top-quintile-minus-universe
period has a standard deviation of about 3.1 %. With 52 periods, the smallest net excess D could detect with
80 % power was about **1.1 % per period (~14 %/yr)**, larger than published premia. So the result rules out
*large* edges in these 63 stocks, not small ones. More stocks is the remedy.

# Addendum A: independent-universe replication (pre-registered 2026-10-23, before download or run)

* **Universe U2:** liquid NSE stocks that are **not** in `app.universe.STOCKS`. The candidate list is fixed in
  `scripts/fetch_extra_universe.py` (committed with this addendum); any name in `STOCKS` is removed in code,
  and whatever Yahoo returns is used. Names enter a rebalance only once they have the 252-session history.
* **Bias warning:** U2 is also *today's* names, and mostly mid-caps, so survivorship bias is stronger than in
  the main plan. A pass here is weaker evidence than the numbers suggest.
* **Unchanged:** the six families, the D/V/C periods, the pass rules, the 0.15 % per-side cost (V's double-cost
  check stands in for mid-caps' wider spreads), the top-quintile long-only portfolio and the equal-weight
  benchmark (of U2 itself).
* **Meaning:** a family passing D, V and C on U2 is evidence that the ranking works in the broader market, which
  would argue for widening the app's universe. Failing strengthens "no simple swing edge" for this data.
