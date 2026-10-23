# Intraday research plan (pre-registered)

Written and committed **before** any test below was run. Changing a threshold, period or family after seeing
results makes the result worthless; any later idea gets its own new, dated plan and a fresh confirmation period.

## Why the current setups lose (measured before this plan)

* All 14 setup/side combinations: net -0.11 %/trade over 4,821 trades, 59 sessions.
* Gross (before the 0.12 % round-trip cost): **+0.008 %/trade, i.e. no edge at all.**
* Median stop distance is 0.23 % of price, so costs alone are **0.52 R per trade**. A 2R-target system then
  needs > 51 % winners to break even. That geometry, not the entry signals, is the first thing to fix.
* Only 60 sessions of 5-minute data exist (Yahoo limit), far too few to tune anything on.

## Data and periods (three independent looks, each used once)

| Period | Data | Range | Used for |
|---|---|---|---|
| D: discovery | daily OHLC, 63 stocks + Nifty | 2016-10-19 to 2022-12-31 | pick survivors |
| V: validation | daily OHLC | 2023-01-01 to 2026-07-23 | opened once, survivors only |
| C: confirmation | 5-min archive | 2026-07-24 to 2026-10-19 | realistic execution, survivors only |

Daily open-to-close trades are exact with daily bars: entry = official open (reachable with a pre-open
market-on-open order), exit = close. Stock-days with |gap| or |open-to-close| > 20 % are dropped as bad
prints or circuit days.

## Hypothesis families (each has an a-priori economic reason)

All are open-to-close, square-off the same day, every position equal capital, 0.06 % cost per side
(0.12 % per round trip per position, both legs of a long/short pay it).

1. **F1 relative-gap reversal (long/short)**: rank stocks by gap minus Nifty's gap; long the bottom
   quintile, short the top quintile. Why: intraday returns tend to reverse overnight moves (liquidity
   provision; "tug of war" between overnight and intraday clienteles).
2. **F2 large-gap fade**: |gap| >= 1 % (the threshold the live gap playbooks already use): short gap-ups,
   long gap-downs.
3. **F3 large-gap go**: the mirror of F2 (counted as its own test).
4. **F4 one-day reversal (long/short)**: rank by the previous day's close-to-close return; long the bottom
   quintile, short the top quintile. Why: short-term reversal / liquidity effect.

Each in two variants: **all stocks**, and **high-volatility half** (stock's 14-day ATR % above that day's
cross-sectional median, using data up to the previous close). Why: costs are fixed, so bigger expected
moves make them a smaller share of the trade.

**8 tests in total.** No other variants are run on D.

## Pass rules (fixed now)

Daily P&L series = average net return of all positions opened that day; t-statistic over days (trades on
one day are not independent).

* **D (discovery):** average net > 0, t >= 2.50 (Bonferroni, one-sided 5 % over 8 tests), positive net in
  >= 60 % of calendar years.
* **V (validation, survivors only):** average net > 0, t >= 1.65, positive in >= 60 % of half-years, and
  still net > 0 at 0.08 % cost per side.
* **C (confirmation, survivors only, 60 sessions = weak test):** replay with 5-minute bars, entry at the
  09:15 bar's open and, separately, at the 09:20 bar's open (late fill), exit at the 15:10 bar's close.
  Must be net > 0 at the 09:15 entry and t > -1 at the 09:20 entry.

Only a family that passes D, V and C may become a live suggestion. If none does, the honest live logic is:
**show setups for information, suggest no trades**, and say why.

## Also measured (descriptive, not used to pick anything)

* Existing 5-minute setups re-simulated with a minimum stop of 0.8 % of price (cost <= 0.15 R) and
  square-off exits: does fixing the geometry alone rescue any setup? 60 sessions only, so it is reported,
  not adopted.

---

# Results (run once, 2026-10-23, `scripts/intraday_open_close_probe.py`, committed before the run)

| Family | D (2016-22) net, t | V (2023-26) net, t | C (last 60 sessions, real 5-min fills) |
|---|---|---|---|
| F1 relative-gap reversal | +0.115 %, t 8.9: PASS | +0.044 %, t 3.4: PASS | 09:15 fill -0.170 %, t -4.9: **FAIL** |
| F1 / high-vol | +0.133 %, t 7.1: PASS | +0.046 %, t 2.4: PASS | -0.224 %, t -3.9: **FAIL** |
| F2 large-gap fade | +0.193 %, t 4.8: PASS | +0.083 %, t 1.6: fail | closed |
| F2 / high-vol | +0.194 %, t 3.9: PASS | +0.123 %, t 1.9: PASS | -0.352 %, t -2.5: **FAIL** |
| F3 large-gap go | -0.433 %: fail | closed | closed |
| F4 one-day reversal | -0.105 %: fail | closed | closed |

**Outcome: no family passed all three gates, so none becomes a live suggestion.**

## What the numbers say (written after the run; interpretation, not a new test)

1. **A real anomaly, shrinking.** F1's gross return per position: ~0.25 % (2016-2020), ~0.20 % (2021-22),
   ~0.17 % (2023-25), **0.09 % (2026)**. Net of the 0.12 % round trip, 2026 is negative. Same shape for
   F2/high-vol (2026 gross -0.04 %).
2. **The daily-bar test was optimistic about fills.** The signal (gap) is only known once the opening price
   exists, so entering "at the open" is not exactly achievable. On the same 60 sessions, daily-bar returns
   give gross +0.023 % and the 09:15 5-minute fill gives -0.050 %. The official open and the 09:15 bar's open
   differ by a median 0.15 % (p90 0.6 %). My plan called the daily open "reachable with a pre-open order";
   that was too generous, and the confirmation gate is what caught it.
3. **Costs are the whole story for the existing 5-minute setups.** `scripts/intraday_geometry_probe.py`
   (descriptive): widening stops to >= 0.8 % cuts costs to 0.15 R but gross stays ~0 (-0.004 % per trade over
   4,825 trades; 59 sessions). The entries themselves carry no edge, so geometry alone does not rescue them.
4. **What would change the conclusion:** forward (paper) evidence on F1/F2 using real pre-open indicative
   prices, which the free data source does not provide; or a much larger 5-minute history.

## Live-logic decision

* Keep the rule: an intraday suggestion ("Long/Short setup") requires a **supported** backtest record; today
  none is, so the scanner shows **candidates**, never trade calls.
* Added `app/intraday/economics.py`: every plan now shows the win rate it needs to break even after costs
  next to the playbook's actual backtest win rate (pure arithmetic, nothing fitted).
