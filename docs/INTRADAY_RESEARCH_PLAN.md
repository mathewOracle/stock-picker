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
