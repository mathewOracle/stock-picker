# US swing research plan (pre-registered 2026-10-27, before any US research was run)

The US app runs the SAME engine as the India app (app/market/us.py is only data). This plan fixes, before any US
backtest, factor run or forward pick exists, what will be run on US data and what each outcome means. It mirrors
docs/SWING_RESEARCH_PLAN.md (India) so the two markets can be compared, and adds nothing chosen after seeing US
results. Commit history is the proof of order: this file is committed before `data-us/research/` has any output.

## Why this is a real out-of-sample test

Every rule, threshold, signal and momentum family was designed and selected on **Indian** data. None was tuned on
US data. So whatever passes here passes out of sample, in a different market, regulator, currency and era of
retail participation. Equally, a US failure is not a reason to change the India app (or vice versa).

## Universes (frozen today, in app/market/us.py)

* **U1 (the app):** the 78 US large caps in `STOCKS` (mega caps across all 11 GICS sectors), benchmark S&P 500
  (`^GSPC`), volatility `^VIX`.
* **U2 (independent):** `U2_CANDIDATES` minus U1, about 200 other S&P 500 names, frozen today. Stocks that later
  collapse, are acquired or leave the index stay in every forward test: no survivorship going forward.
* Known bias, accepted and stated: both lists are *today's* large caps, so every historical backtest is flattered
  by survivorship. The control group (the universe average) carries the same bias, so edges stay comparable.

## Costs

0.05% per side (`MARKET.swing_cost_per_side`): $0 commission, half-spread + slippage on large caps, SEC Section 31
and FINRA TAF sell fees. Deliberately above what a large-cap market order really costs. Every pass rule must
also survive **double** cost.

## What is run, once each, in this order

1. **Swing ledger backtest** (`python -m app.research backtest`): the app's verdict rules on U1, weekly evaluations,
   next-open entry, stop/T1/40-session exit, control group = all evaluations. Pass rule unchanged from India:
   >= 30 trades and t >= 1.65 on the edge over the control, judged on the full period; the 2024-11-01+ hold-out is
   reported, not used to pick.
2. **Six momentum/price families on U1 and U2** (`python -m scripts.swing_factor_probe` / `extra`), periods and gates
   exactly as the India plan: discovery to 2021-12-31, validation to 2024-10-31, confirmation after; V only for D
   survivors, C only for V survivors.
3. **Intraday backtest** (`python -m app.research intraday`): the 7 playbooks on the archived 5-minute bars, same
   parity rules as India, with the US Reg SHO Rule 201 filter applied to shorts (a short the desk would refuse is
   never counted). Pass rule unchanged (>= 100 trades over >= 20 days, positive after costs, both halves positive).
   Yahoo keeps 60 days of 5-minute bars, so the first verdict needs the archive to grow; until then "not enough
   trades" is the expected, honest answer.
4. **Forward test of momentum on U2** (`python -m app.research forward`), Addendum B of the India plan word for
   word, except: families M1, M2, M6 (selected on India data: a cross-market replication), signal after 16:15 ET
   on a completed NYSE session, picks in `docs/us/forward/momentum_picks.csv` (append-only, git-tracked),
   verdict once at 15 completed periods with the V rule (net excess > 0, t >= 1.65, >= 60% of calendar years
   positive, still > 0 at double cost).

## What each outcome means for the US app

* A swing verdict rule passes (1): the US swing Buy can be shown as validated, like India's rules would be.
* Nothing passes (the India result): the US app stays *information first*; no stock is shown as a validated Buy,
  the order desk keeps refusing tickets, and that is the correct behaviour, not a bug.
* An intraday playbook passes (3) once the archive is long enough: only that playbook's setups become tradeable.
* A momentum family passes (4): the first validated US ranking; shown beside the verdicts, never as an order.

## Regulation is not research

The US trading rules (FINRA pattern day trader, Reg SHO Rules 200/201/203, Reg T, T+1 settlement, Rule 612,
wash sales) are enforced by app/rules/us.py on every ticket regardless of any backtest result. See docs/us/US_RULES.md.
