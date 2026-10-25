# How to actually trade off this app

This is a walk-through for *using* the signals, not a repeat of the architecture docs in the
main [README](../README.md). Read that first if you want to know how a score is computed; read
this if you want to know what to click, when, and why.

**Not investment advice.** This tool surfaces evidence and gets out of the way; the decision,
the capital, and the risk are yours.

---

## 0. The one rule that matters more than any indicator

> A rule-based "Buy" or "setup" is only ever a **starting point**. The app downgrades it
> automatically the moment the evidence disagrees (see "Reading a downgrade" below). **Never
> override that downgrade with your own gut feel** — the whole point of the evidence layer is
> that gut feel is what loses money.

If you remember nothing else: **Strong Buy / Buy / Long setup / Short setup = validated by
rules AND backtest. Everything else is a "maybe, with reasons" — treat it as research, not a
trade ticket.**

---

## 1. Swing / positional trades (holding days to weeks)

> **Honest status (backtest of 2,929 rule "Buy" trades, Nov 2017 to Oct 2026): the rule is not
> validated.** It made **+0.44%** per trade after costs. The control group made **+0.40%**: the same
> stop/target/time-exit plan taken on every stock-week, signal or not. So the rule's edge is
> **+0.04% (t = 0.33)**, which is indistinguishable from luck. Validation therefore downgrades every
> rule Buy to Watchlist, and **Suggested buys** is normally empty. That is the app's real answer:
> there's no validated swing pick. The steps below are how to trade a Buy *if* one ever passes, and
> they match exactly what the backtest does.

A swing trade is **held overnight, typically for 1-3 weeks** (backtest average: 15 sessions). Every
trade has three ways out, whichever comes first: the **stop**, **Target 1**, or the **time exit at
session 40** (about two months).

### Step 1 — Open the dashboard (`/`)
Check **Market regime** first (top of the page). A "Correction / Bearish" regime is a message to
size down and be selective, not a reason to stop reading. The gates below already account for
price action, but they don't know your personal risk budget. The **Validation** box underneath
says whether the rules currently pass their backtest.

### Step 2 — Work the **Suggested buys** list, not the candidates
- **Suggested buys** = `Strong Buy` / `Buy` that passed *every* gate, including validation. These are
  the only suggestions to act on (see §3).
- **Rule-based candidates (not validated)** = the rules fired, but validation overruled them. It's
  research, not a trade list. Read §4 before touching one.
- Each card shows the **composite score** (0-100) and the three pillar scores (Fundamental /
  Technical / Chart).

### Step 3 — Open the stock page, read the gates before the chart
Click through to `/stock/{symbol}`. Scroll to the **gates** section before you look at anything
else. It lists exactly which thresholds passed and which didn't, e.g.:

| Gate | Needs |
|---|---|
| Composite / Fundamental / Technical / Chart | >= 57 / 52 / 52 / 45 (Buy), higher for Strong Buy |
| Reward/risk | >= 1.5 (2.0 for Strong Buy) |
| No hard red flags | Falling knife, Loss-making, High leverage, Weak Piotroski all veto |
| Not extended (Strong Buy only) | < 3 ATR above the 20-EMA: don't chase a spike |

If the verdict badge differs from the rule verdict, the rules fired but validation overruled them.
Read §4 before doing anything.

### Step 4 — Take the trade plan as printed, not as a starting point to improve
The **Trade plan** box prints **Entry (last close) / Stop / Target 1 / Target 2 / Reward:Risk**.
The stop sits 0.5 ATR under a real support level, or 2 ATR under price if there's no nearby
support. Moving it further away "to give it room" is the most common way a planned 1R loss
becomes a 4R loss. Don't recompute the levels if your fill is a little different: the backtest
doesn't either.

### Step 5 — Size the position
Use the **Capital** and **Risk per trade** boxes inside the Trade plan (the same sizer as
intraday). It works out capital x risk% / (entry - stop) shares, capped at what your capital can
actually buy (no leverage). Risk at most 1% of capital per trade.

### Step 6 — Enter and exit (printed on every stock page with its own numbers)
Example: last close **Rs 2,000**, plan **Stop 1,900 / T1 2,200 / T2 2,300**, capital
Rs 1,00,000, risk 1%.

1. **Size it.** Rs 1,000 risk / Rs 100 per share = **10 shares** (Rs 20,000, well inside your
   capital, so no cap).
2. **Enter at the next session's open.** Use a market order with the **delivery (CNC)** product, not
   intraday/MIS, because you'll hold overnight. **Skip the trade** if the stock opens at or below
   the stop (1,900) or at or above T1 (2,200). The backtest skips those too.
3. **The same day, place both exits for the whole quantity** as one **GTT OCO** order
   (good-till-triggered, one-cancels-the-other): a stop trigger at **1,900** and a target trigger
   at **2,200**. A plain stop-loss order expires at the end of each day, and a GTT doesn't. A GTT
   places a *limit* order when triggered, so set the stop leg's limit a little below 1,900 (e.g.
   1,890) so it still fills in a fast fall. Check how your broker labels these.
4. **Time exit: if neither has triggered by the close of session 40** (entry day = session 1),
   sell at market that day. Put the date in your calendar when you enter. In the backtest, 9% of
   trades ended this way.

**What about T2?** It's shown as a stretch level only. The backtest sells the *whole* position at
T1. "Half at T1, move the stop to breakeven, let the rest run" is a different plan, and it has
never been tested here, so the backtest numbers don't describe it.

**What the backtest says to expect** (all 2,929 trades): 55% ended at the stop, 35% at T1 and 9% at
the time exit. 42% were winners. **5% gapped through the stop** and sold at the open, below the
stop. The worst of those lost 61% after an overnight crash. With a 1%-risk position, that's
a single loss of several R. It's the price of holding overnight, and it's why risk per trade
should stay small.

**What if...**

| Situation | Do this |
|---|---|
| The open is a bit off the last close (e.g. 2,010) | Enter anyway if it's between the stop and T1. Keep the printed stop and T1; your real risk is now Rs 110/share, which is fine. |
| It opens at 1,890 (below the stop) or 2,210 (above T1) | No trade. Don't chase it or wait for a pullback; the plan is void. |
| The verdict drops to Watchlist / Hold mid-trade | Informational only. Your stop, T1 and session 40 still decide the exit. |
| The stock is already in your portfolio from an earlier signal | Don't add a second position. The backtest holds one trade per stock at a time. |
| The stop got hit, then the price went to T1 anyway | That's a loss, and it's counted in the backtest numbers too. Wait for a fresh signal. |
| Results are due inside the holding window | The backtest didn't skip these, so skipping is your own (untested) choice. If you hold, expect a bigger gap risk. |

---

## 2. Intraday trades (same-session, 5-minute bars)

> **Honest status (backtest of 4,821 trades, Jul-Oct 2026): 0 of 14 setup/side combinations are
> "supported".** Most lose money after costs; the rest have too few trades to judge
> (`docs/INTRADAY_RESEARCH_PLAN.md`). So **Active setups** is normally empty, and that is the app's
> real answer: no intraday trade. The steps below are how to trade a setup *if* one ever gets
> supported, and they match exactly what the backtest does.

Intraday means **in and out the same day**. Every trade has three ways out, whichever comes first:
the **stop**, **Target 1**, or the **time exit at 15:15**. Nothing is ever held overnight. Intraday
short-selling in the Indian cash market *must* be bought back the same day anyway.

### Step 1 — Check the market status banner at the top of `/intraday`
It tells you the phase in plain words: *Pre-market*, *Opening range forming* (wait, don't enter),
*Open: trading window* (the only phase accepting new entries), *Open: no new entries* (14:45
onward — manage existing positions only), *Closed*.

### Step 2 — Check **Active setups** before the full scanner table
This section only shows setups that are:
1. A live playbook trigger (see the 7 playbooks under "Intraday playbook" further down the page), **and**
2. Backtest-supported for that exact playbook + side (the **evidence badge** under the trigger text), **and**
3. Reward/risk >= 1.5, **and** aligned with the day's bias, **and**
4. Signalled by a bar that closed by 14:45, the backtest's last entry time. After that, including
   all evening when you're looking at the last session, every stock reads *No trade*. The reason
   still names the setup, so you can review it.

If a stock fires several setups at once, the card shows a backtest-supported one ahead of an
unsupported one, even if the unsupported one has the bigger reward/risk.

These are the closest thing this app has to "go trade this". Everything else in the Scanner
table below is either waiting on a rule, waiting on validation, or explicitly not tradeable.

### Step 3 — Reading the Scanner table's new confidence columns
Added so you don't have to click into every stock to sanity-check a verdict:

| Column | What it tells you | How to use it |
|---|---|---|
| **Backtest** | This exact playbook+side, replayed historically across **all 63 stocks pooled together** (not just this one) — trade count, average return after costs, day-clustered t-stat | Pooled because any single stock only fires a setup a handful of times over the archive, not enough to trust statistically; pooling gives real sample size at the cost of being a statement about the *strategy*, not this specific stock. Every stock currently showing the same playbook+side will show this **identical** number. "supported" = the historical edge clears the bar. "not supported" = this setup has **lost money** historically (a real, significant negative, not just "inconclusive") even though it's firing right now — that's why the verdict says "candidate" not "setup". "no live setup" just means nothing is firing, nothing to judge. |
| **Sentiment** | Daily news headline sentiment (Loughran-McDonald dictionary), same number the swing page uses | This is a **daily**, not intraday, signal — a stock can have very positive news and still chop sideways for an hour. Use it as a tie-breaker between two similar setups, never as an entry trigger by itself. Hover for headline count/sources: under 5 headlines / 3 sources means "thin coverage", treat as no signal. |
| **ML** | The project's machine-learning trade-outcome filter | Will read **"not used"** for the foreseeable future — the model has been tested against a strict hold-out and unseen-stock validation and failed both (see `/research` for the numbers). This is the honest state, not a bug. If it's ever adopted, the column will start showing a real per-stock win probability instead. |

**Bottom line on the three columns:** Backtest is the one that should change your behaviour
today. Sentiment is a secondary filter. ML is currently just documentation of "we tried, it
didn't work" — don't wait for a number that isn't coming.

### Step 4 — If a "candidate" (not a "setup") still tempts you
A `Long candidate` / `Short candidate` verdict means the live rules fired but the Backtest
column says "not supported" or "not backtested". Historically, trading this exact setup+side has
either lost money or has never been tested. If you take it anyway:
- Size smaller than you would for a validated "setup" (this is uncompensated risk, not a free edge).
- Don't average down — there's no statistical backstop telling you it mean-reverts.

### Step 5 — Position size and place the order
Use the **sizer** form at the top of the Active setups section (capital, risk% per trade). It
computes shares from the entry/stop on each card, capped by what your capital can actually buy
(no leverage assumed). Risk at most 1% of capital per trade.

### Step 6 — Enter and exit (the same day, always)
Every setup card prints these three steps with its own numbers. Here they are with an example: a
**Long** opening-range breakout on a Rs 1,000 stock, card showing **Entry 1,000 / Stop 994 /
T1 1,012 / T2 1,018**, capital Rs 1,00,000, risk 1%.

1. **Size it.** Risk Rs 1,000 / Rs 6 per share = 166 shares. But 166 x Rs 1,000 is more than
   your capital, so the sizer caps it at **100 shares** (no leverage assumed). Your real risk is
   now Rs 600. That's fine, because smaller is always allowed.
2. **Enter as the next 5-minute bar opens**, by **14:45** at the latest. Use a market order, with
   the **Intraday / MIS** product (not delivery/CNC), and *Buy* for a long or *Sell* (short) for
   a short. The signal comes from a bar that has already *closed*, which is why you act on the
   next one. **Skip the trade** if price is already at or beyond the stop (994) or T1 (1,012):
   the backtest skips those too.
3. **Straight after the fill, place both exits** for the whole quantity:
   - a **stop-loss order at 994** (SL-M, or SL with a small limit buffer so it fills in a fast
     move), and
   - a **limit order at T1, 1,012**.

   When one fills, **cancel the other**. If your broker offers an OCO, bracket or cover order,
   it does this for you.
4. **Time exit: at 15:15, close whatever is still open at market.** That means sell a long, or
   buy back a short. Don't wait for the broker's auto square-off at about 15:15-15:20: it
   usually charges an extra fee and fills wherever it fills. In the backtest, 20-35% of trades
   ended this way, so it is a normal exit, not an emergency.

**What about T2?** It's shown as a stretch level only. The backtest exits the *whole* position
at T1. Holding for T2 (or "half at T1, move the stop to breakeven", which is the *swing* exit) is
a different plan that has never been tested.

**What if...**

| Situation | Do this |
|---|---|
| Your fill is a bit off the printed entry (e.g. 1,002) | Keep the printed stop and T1 levels. Don't recompute them; the backtest doesn't. |
| It's 14:46 and the setup just appeared | No trade. The card will say so. |
| It's evening and a *No trade* reason names a setup from the last bars | Leave it. Tomorrow's 09:15 open is a different trade; the backtest never enters overnight. |
| The stop got hit, then price went to T1 anyway | That's a loss, and it's in the backtest numbers too. Don't re-enter the same setup that day. |
| Your daily loss limit (e.g. 3R) is hit | Stop for the day, including setups that look perfect. |
| Data looks stale (banner says "Data is from HH:MM") | Refresh. Check the live price in your broker before acting. |

### Step 7 — Non-negotiable intraday discipline (also printed on the page itself)
- Set a daily loss limit (e.g. 3R) and **stop trading for the day** when it's hit.
- Place the stop with the order. Never widen it. Never average down a loser.
- No new entries after 14:45 IST. Close everything by 15:15, before the broker's auto square-off
  (roughly 15:15-15:20).
- Yahoo's 5-minute bars can lag by a few minutes — confirm the actual price in your broker
  terminal before you click buy/sell.

---

## 3. Verdict cheat-sheet (both pages)

| Verdict | Meaning | Action |
|---|---|---|
| **Strong Buy** / **Long setup** / **Short setup** | Rules fired *and* backtest/news/ML all agree | The closest thing to a go-ahead. Still size per your own risk rules. |
| **Buy** | Same as above, one tier down on conviction | Go-ahead, standard position size. |
| **Long candidate** / **Short candidate** | Live rules fired, but backtest/news/ML disagreed | Research-grade, not trade-grade. Read §2.4 (intraday) or §4 (swing) before touching it. |
| **Watchlist** | Good business, chart/technical not ready, OR a Buy was downgraded by validation | Wait. The stock page lists exactly what it's "waiting for". |
| **Hold** | Composite mediocre, no hard red flag | No action either way. |
| **Avoid** / **No trade** | Hard red flag, or no setup firing, or market phase doesn't allow entries | Don't force a trade; the "Why" column always says the specific reason. |

## 4. Reading a downgrade (swing page)

When `rule_verdict` says Buy but `verdict` says Watchlist, the stock page's gate list will show
one or more of these, each with the actual number next to it:
- **Backtest (universe or this stock)** — the price rule hasn't beaten random entries at a
  95% one-sided confidence level, or this stock's own trade history doesn't back it up.
- **News sentiment** — headline sentiment is below -0.30 (a real, not noisy, warning level).
- **ML model** — only appears when a model is adopted (currently: none).

This is the system doing exactly what it's for. A missing backtest is treated as *unvalidated*,
never as a free pass.

## 5. Making your own swing trading rules

There are two kinds of rule, and they need different treatment. **Risk rules** decide how much you
lose when you're wrong. You choose them, and you can't backtest them into being "right". **Signal
rules** decide what to buy, and they have to earn their place with evidence.

### 5a. Your risk rulebook: write it down before the first trade

Fill this in once, keep it next to your broker window, and change it only on a weekend, never
mid-trade. The starting values are common, conservative choices, not optimised numbers.

| Rule | Starting value | Why |
|---|---|---|
| Risk per trade | <= 1% of capital | A 5% gap-through loss (see §1 Step 6) then costs a few percent of the account, not a quarter of it. |
| Open positions at once | <= 5, so <= 5% total open risk | A market-wide fall hits every position on the same day. |
| Positions per sector | <= 2 | Sector moves are correlated. Five banks is one trade with five commissions. |
| Positions per stock | 1 | That's what the backtest does. No adding to winners or losers. |
| What qualifies | `Strong Buy` / `Buy` under **Suggested buys** only | Candidates and Watchlist have failed validation (§4). |
| Entry | Next session's open; skip if it opens beyond the stop or T1 | Same as the backtest (§1 Step 6). |
| Exit | Stop / T1 / session 40, whole quantity, GTT OCO | Same as the backtest. Any other exit is a new, untested plan. |
| Account brake | Down 10% from the peak: halve the risk per trade. Down 15%: stop and review. | Losing streaks are normal: at a 42% win rate, 8 losses in a row is likely over a few hundred trades. The brake stops a streak becoming a hole. |
| Never | Widen a stop, average down, override a downgrade, trade on a tip | Each one turns a small planned loss into a big unplanned one. |
| Journal | Every trade: date, verdict, planned vs actual entry, exit reason, result in R | After 20 trades, compare your average R with the backtest's. If yours is much worse, the gap is your execution, not the signal. |
| Review cadence | Run the screener once a week, same day | The backtest evaluates weekly; daily checking adds temptation, not edge. |

Changing a risk rule is allowed (it's your money), but write down the date and the reason. If
you change it after a loss, wait a week first.

### 5b. Changing or adding a signal rule: the research process

Every signal rule in this app went through the same steps. Skipping one is how a rule that only
looks good on the past ends up costing money in the future.

1. **Write it so a computer can follow it.** Entry condition, stop, target, time exit, which stocks,
   costs. If any step says "use judgement", it can't be tested, and it will drift.
2. **Pre-register before you run anything.** Create a new dated plan in `docs/` (copy the structure of
   [`SWING_RESEARCH_PLAN.md`](SWING_RESEARCH_PLAN.md)): the question, the exact rule, the test periods
   and the pass bar. Commit it **before** the first run; the git timestamp is your proof. A threshold
   changed after seeing results makes the result worthless. A new idea gets a new plan.
3. **Build it in the shared code path**, so the backtest tests exactly what the dashboard shows:

   | What you're changing | Where |
   |---|---|
   | The signal (technical + chart scoring, Buy test) | `app/pricecheck.py` (`assess_price`, `price_signal`); thresholds in `GATES` in `app/scoring.py` |
   | Stop and target placement | `app/tradeplan.py` (`make_plan`) |
   | Entry, exit and costs in the replay | `app/research/backtest.py` (`simulate`, `MAX_HOLD`, `COST_PER_SIDE`) |
   | What the stock page tells you to do | `swing_entry_exit_steps` in `app/templates/_macros.html` (keep it matching `simulate`) |

4. **Beat the right hurdle.** The question isn't "did it make money?", because in a bull market almost
   everything did. It's "did it beat the same plan on every stock-week, after 0.15% per side of
   costs?" Pass bar: positive edge, t >= 1.65, positive in >= 60% of years, still positive at double
   costs.
5. **Open the periods in order, once each.** Discovery 2017-21, then validation Jan 2022 to Oct 2024,
   then confirmation Nov 2024 onward. Only what passes one period gets to see the next. A rule that
   fails is finished: a tweaked version is a new idea and needs a new plan.
6. **Know the traps** that make a rule look better than it is:
   - **Survivorship bias:** the universe is *today's* large caps replayed backwards, so stocks that
     collapsed and left the index are missing. Results are flattered, so a pass is a weak yes and a
     fail is a strong no.
   - **Fundamentals can't be backtested** here: only today's snapshot is stored, so using it in the
     past would mean seeing the future.
   - **Many tries:** test 20 variants and one will "pass" by luck. Count every variant you tried, and
     demand more evidence the more you tried.
   - **Lookahead:** the signal can only use data up to the signal day's close; the trade starts at the
     next open. `python -m scripts.backtest_sanity` checks the engine finds a planted edge and
     doesn't invent one.
7. **Then test it going forward.** Record picks *before* the outcome exists (see
   `docs/forward/momentum_picks.csv`), and judge them once, at a pre-set date.
8. **Only then let it change a verdict**, and show its evidence on `/research`.

**Already tried here, so don't repeat these expecting a different answer:** the current composite
rule (no entry skill, edge t = 0.33); six published price rankings on the 63 stocks (none passed
discovery); momentum on 158 mid-caps (passed discovery, failed validation; a forward test runs until
about Jan 2028); four machine-learning filters (all failed the hold-out); news sentiment (used only as
a veto for strongly negative news). The details are in `docs/SWING_RESEARCH_PLAN.md` and on
`/research`.

## 6. Where to dig deeper

- `/research` — the full evidence behind every gate: backtest methodology and results, the news
  sentiment correlation study, and the ML model's walk-forward numbers, including why it wasn't
  adopted.
- [README.md](../README.md) — architecture, scoring formulas, how each check is computed.
- `python -m scripts.backtest_sanity` — proves the backtest engine can detect a planted edge,
  if you want to sanity-check the research pipeline itself before trusting its verdicts.
