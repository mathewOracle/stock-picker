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

# Results of Addendum A (run once, 2026-10-23, commit fa2baaa)

U2 = 158 of 162 candidates usable (LTIM, GUJGASLTD, HONAUR not returned by Yahoo; one name too young).
Data note: PNB, SKFINDIA and YESBANK each have a daily move above 40 % (Yes Bank's 2020 collapse is real; the
others may be adjustment errors). No bad-print filter was pre-registered for swing, so none was added.

| Family (U2) | D net excess, t, years + | V net excess, t, years + | Result |
|---|---|---|---|
| M1 12-1 momentum | +0.96 %, 2.43, 100 %: PASS | +0.46 %, 1.32, 67 % (2x cost +0.40 %) | **fail (V t < 1.65)** |
| M2 6-1 momentum | +0.93 %, 2.57, 100 %: PASS | +0.44 %, 1.31, 67 % (2x cost +0.34 %) | **fail (V t < 1.65)** |
| M6 risk-adjusted momentum | +0.85 %, 2.25, 100 %: PASS | +0.27 %, 0.96, 100 % (2x cost +0.15 %) | **fail (V t < 1.65)** |
| M3 52-week-high | +0.22 %, 0.46: fail | closed | |
| M4 low volatility | -0.43 %, -1.14: fail | closed | |
| M5 one-month reversal | +0.29 %, 0.73: fail | closed | |

**C (2024-11 onward) stays closed for these families**, as pre-registered. Opening it after a near miss would
move the goalposts.

## Interpretation (after the run; not a new test)

* Momentum is the **only** lead in all the research so far: positive in both periods on the wider universe,
  surviving double costs, consistent with the literature (stronger outside mega-caps). It is **not validated**.
* **Survivorship bias hits momentum hardest:** a list of today's mid-caps includes past winners that kept
  winning and excludes momentum names that later collapsed out of the market. The bias is largest in early
  years, which fits D (+0.96 %) shrinking in V (+0.46 %). The true edge may be much smaller.
* In the app's 63 mega-caps, momentum showed nothing (main plan). The live swing rule's entries show no skill.

## What would settle it

1. **Point-in-time membership** (historical Nifty 200/500 constituents, including stocks that later fell out),
   so the test universe is what an investor could actually have bought on each date.
2. **A forward test from today**: rank U2 every 20 sessions, record the picks before outcomes exist, evaluate
   after 12-18 months with the same pass rule as V. Nothing seen so far can contaminate it.

# Addendum B: forward test of momentum on U2 (pre-registered 2026-10-23, before any pick was recorded)

The only way to test momentum without survivorship bias or any chance of having seen the outcome: record the
picks **before** the future exists, then wait. Item 2 of "What would settle it" above.

* **Families:** M1, M2 and M6 only (the three that passed D on U2). Same features, same top quintile,
  same >= 30 eligible names. No other variants.
* **Universe:** U2 exactly as fixed in Addendum A (the candidate list, minus `app.universe.STOCKS`). It is
  frozen *today*, so stocks that collapse or delist from here on stay in the test: no survivorship bias going
  forward. A stock is eligible at a rebalance if it has a non-zero-volume bar on the signal day and the full
  252-session lookback (same rule as the backtest).
* **Recording (append-only, git-tracked):** `docs/forward/momentum_picks.csv` stores every eligible stock's
  features and the pick flags per family. Rows are never edited or deleted; only new rebalances are appended,
  and the commit history is the proof of when each was written.
* **Signal:** the latest **completed** session (after 16:00 IST), from data refreshed in the same run. A
  rebalance is refused (not recorded with a smaller universe) if fewer than 90 % of the U2 stocks with enough
  history have a bar that day, or if the latest session is more than 5 calendar days old. (Clarified before the
  first pick: "stocks with enough history" means >= 252 traded sessions and at least one bar in the last 20
  sessions, so a stock that delists later cannot block every future rebalance.)
* **Holding:** entry at the open of the first session that starts **after the picks were recorded**, exit at
  the close 20 sessions later (entry day included). The next rebalance is due once that exit session has closed,
  so holding periods never overlap. A missed evening just shifts the next rebalance later; a rebalance is never
  back-filled.
* **Returns:** close(exit) / open(entry) - 1 on adjusted prices. If a stock has no bar on the entry day, it
  enters at its first open inside the window; if it stops trading (delisting, suspension), it exits at its last
  close inside the window. A stock with no bar at all inside the window is dropped from both sides and counted.
* **Scoring:** identical to V: equal-weight top quintile minus equal-weight eligible universe, 0.15 % per side
  on new entries only, t over non-overlapping periods.
* **One look:** the verdict is computed **once**, when **15 periods** have completed (about 15 months), with the
  V rule: net excess > 0, t >= 1.65, >= 60 % of calendar years (>= 4 periods) positive, still > 0 at double cost.
  Interim numbers are shown, labelled *interim*, and are never a reason to stop early, extend or change anything.
* **Meaning:** a family that passes is the first validated swing ranking and may be shown beside the verdicts
  (still information first). If all three fail, momentum joins the list of things that did not work here.
