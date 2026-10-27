# US trading rules the app enforces

The US app is a **dry run**: it records broker-neutral order tickets in a local journal and sends nothing to any
broker. Every ticket is still judged against the US rules below, and a ticket that breaks one cannot be recorded
(the server refuses it whatever the browser sends). Code: `app/rules/us.py`; tests: `tests/test_us_rules.py`,
`tests/us/test_us_app.py`. Re-check these yearly: thresholds, fees and FINRA proposals change.

Not legal or tax advice. The app is a research tool; talk to an SEC-registered investment adviser before investing.

| Rule | What it says | What the app does |
|---|---|---|
| **FINRA Rule 4210(f)(8)(B)** pattern day trader | 4+ day trades in 5 business days in a margin account makes you a PDT; a PDT needs $25,000 equity | Every intraday ticket is a day trade (flat by the square-off). Under $25k in a margin account the desk counts its journal's day trades in the last 5 NYSE sessions and **blocks the 4th**. FINRA has proposed replacing the $25k rule; until your broker changes policy it applies |
| **Reg SHO Rule 201** short-sale circuit breaker | After a 10% drop from the prior close, shorts only above the national best bid, rest of day + next day | Our short entries are marketable, so shorts are **blocked** while it is active, in the live verdict **and in the intraday backtest** (one shared function: `app.rules.intraday_block`) |
| **Reg SHO Rules 203(b), 200(g)** locate and marking | A borrow must be located before a short; the order is marked "sell short" | Shorts are `sell_short` / `buy_to_cover`; every short ticket warns to confirm easy-to-borrow and borrow fees |
| **Reg T** margin | Shorts are margin trades (150%); cash accounts must pay with settled funds | Cash account: shorts **blocked**; buys beyond today's settled cash **blocked** (good-faith violation guard) |
| **SEC Rule 15c6-1** T+1 | Trades settle one business day later (since 28 May 2024) | Settlement date shown on every ticket, NYSE holidays included |
| **Reg NMS Rule 612** sub-penny rule | Orders at $1.00+ in whole cents; below $1 in $0.0001 | Every price is snapped to that grid |
| **IRS section 1091** wash sale | A loss is disallowed if the same stock is bought within 30 days before/after | Warns when the journal shows the same symbol within 30 days |
| Holding period | <= 1 year = short-term gains, ordinary income rates | Shown on every ticket (every app trade is short-term) |
| LULD pauses, market-wide circuit breakers | Trading halts on big moves (stock or index) | Intraday tickets warn: no stop can fill during a halt |
| Employer / insider policies (Rule 10b-5) | Some people may not trade some stocks | Optional `data-us/broker/restricted.txt` (one ticker per line) **blocks** those symbols |

## Account type

The ticket asks **Margin** or **Cash** (default Margin, the account that allows shorts). Equity is the "Capital"
field of the sizer. The PDT count only sees orders recorded by this desk: day trades made elsewhere must be
added mentally, and the ticket says so.

## Market hours

Regular session 09:30-16:00 ET (America/New_York, so daylight-saving changes are automatic); NYSE holidays and
13:00 half-days come from `exchange_calendars` (XNYS). Intraday: opening range to 09:45, no new entries after
15:15 (12:15 on a half-day), flat by 15:45 (12:45). Pre-market (04:00) and after-hours bars are never traded or
backtested.

## Before connecting a real broker

Not done on purpose. A broker adapter must map the neutral ticket fields (`symbol, side, quantity, order_type,
limit_price, stop_price, time_in_force, extended_hours`, OCO exits) 1:1, read credentials from the environment
only, start with 1-share tests, reconcile the order book after every action, and keep a kill switch. The broker's
own PDT, borrow and buying-power checks remain the final authority.
