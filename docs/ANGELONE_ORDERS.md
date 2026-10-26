# Placing the app's trades through Angel One SmartAPI

Analysis of which **order** APIs to use, with which parameters, so a swing Buy or an intraday setup is executed exactly
the way the backtest traded it. Only order placement is covered here: no data, analysis or strategy logic was taken from
other code. *What* to trade still comes only from this app's validated verdicts.

**Status:** the parameters are implemented as pure functions in `app/broker/angelone.py`, pinned by
`tests/test_broker_angelone.py`. **Nothing sends an order yet.** The `/desk` page records these exact tickets to a local dry-run journal (`app/broker/desk.py`), which is the rehearsal step before any live sending. A live executor is a separate, deliberate step
(see §6). Today no swing Buy and no intraday setup passes validation, so every ticket would be refused anyway.

## Commands

There is **no broker service to start**: nothing here connects to Angel One. The plans come from the app itself
(start it with `./serve.sh`, see the README's [Run](../README.md#run) section).

```bash
# Check the order parameters (no network, no credentials):
.venv/bin/python -m pytest -q tests/test_broker_angelone.py

# Preview the exact request bodies for a plan (example numbers; take token + tick from the scrip master):
.venv/bin/python - <<'EOF'
from decimal import Decimal
from types import SimpleNamespace

from app.broker.angelone import Instrument, swing_ticket
from app.tradeplan import TradePlan

inst = Instrument("RELIANCE-EQ", "2885", Decimal("0.05"))
report = SimpleNamespace(verdict="Buy", plan=TradePlan(2000, 1900, 2200, 2300, "example"))
ticket = swing_ticket(report, inst, qty=10, open_price=2010)
print(ticket.entry, *ticket.exits, ticket.time_exit, sep="\n")
EOF
```

That prints a `BUY DELIVERY LIMIT` at 2020.05, a SELL GTT triggering at 1900 (limit 1862) and one at 2200, and
"close of session 40". Change `verdict` to `"Watchlist"` and the ticket is refused, with the reason.

## 1. Sources

| Source | What it gave | Verdict |
|---|---|---|
| `smartapi-python` **1.5.5** source (`SmartApi/smartConnect.py`, from Walmart Artifactory) | Exact routes, method signatures, how request bodies are sent, error behaviour | **Authoritative** for field names and SDK behaviour |
| `mathewOracle/trading` (`technicalAnalysis/tradeAPI.py`, `order.py`, `userTrade.py`) | `placeOrder` and `gttRule` are copies of the SDK README sample: hard-coded `SBIN-EQ` / token `3045` / price `"19500"` (SBIN trades near Rs 800). It places the same order **twice** ("Method 1" `placeOrder` + "Method 2" `placeOrderFullResponse`). The GTT is always a `BUY` with `MARGIN`. `order.py` is target/stop *analysis* (Bollinger bands), not order placement. | **Nothing reusable.** It also has live Angel One credentials hard-coded (rotate them). |
| `mathewOracle/dividendAnalysis` (`brokerApi.py`) | The same sample code, plus token lookup without an exchange filter | Nothing reusable |
| Angel One online docs | Unreachable from the Walmart network (blocked), so they weren't checked | Items that depend on them are listed in §5 |

## 2. Swing Buy (DELIVERY, held overnight)

Backtest rule (`app/research/backtest.py`): enter at the next open; skip if it opens at or below the stop or at or above T1; exit the
**whole** quantity at the stop or T1, or at the close of session `MAX_HOLD` (40). T2 is never an order.

| Step | When | SDK call | Key parameters |
|---|---|---|---|
| Entry | After 09:15, once today's open is known | `placeOrderFullResponse` | `variety NORMAL`, `ordertype LIMIT`, `producttype DELIVERY`, `transactiontype BUY`, `duration DAY`, `price` = open + 0.5% (rounded up to the tick, capped one tick below T1), `exchange NSE`, `tradingsymbol XXX-EQ`, `symboltoken` from the scrip master |
| Skip instead | Open <= stop or >= T1, or quantity 0 | no call | `swing_ticket` returns a `skip` reason |
| Stop | Right after the fill | `gttCreateRule` | `transactiontype SELL`, `producttype DELIVERY`, `triggerprice` = stop, `price` = stop - 2% (a limit that still fills in a fast fall), `qty` = `disclosedqty` = filled quantity, `timeperiod` 80 days |
| Target | Right after the fill | `gttCreateRule` | `SELL`, `DELIVERY`, `triggerprice` = T1, `price` = T1 (rounded down) |
| One-cancels-other | Daily, after the close | `gttLists` / `gttCancelRule` | SmartAPI's GTT takes **one** trigger, so the two legs are separate rules. When one triggers, cancel the other. |
| Time exit | Close of session 40 | `gttCancelRule` x2, then `placeOrderFullResponse` | `exit_now()`: `SELL DELIVERY LIMIT` at LTP - 0.5% |

Why not a bare `MARKET` order? A marketable LIMIT fills just like a market order in normal conditions but caps the price
you can get in a spike. Why not an AMO (after-market order) placed the night before? It can't enforce the backtest's
"skip if it opens beyond the stop or T1" rule; placing the order after the open can.

## 3. Intraday setup (INTRADAY, flat the same day)

Backtest rule (`app/research/intraday_backtest.py`): signal on a closed 5-minute bar, enter at the next bar, by 14:45 at the latest;
skip if price is already at or beyond the stop or T1; exit the whole quantity at the stop or T1; flat by `SQUARE_OFF` (15:15).

| Step | When | SDK call | Key parameters |
|---|---|---|---|
| Entry | Next bar, verdict `Long setup` / `Short setup` only | `placeOrderFullResponse` | `variety NORMAL`, `ordertype LIMIT`, `producttype INTRADAY`, `BUY` (long) or `SELL` (short), `price` = LTP +/- 0.5%, never at or past T1 |
| Stop | **After** the entry is confirmed filled | `placeOrderFullResponse` | `variety STOPLOSS`, `ordertype STOPLOSS_LIMIT`, opposite side, `triggerprice` = stop, `price` = stop -/+ 2% |
| Target | After the fill | `placeOrderFullResponse` | `variety NORMAL`, `ordertype LIMIT`, opposite side, `price` = T1 |
| One-cancels-other | Continuously | `orderBook` (or the order-update websocket) + `cancelOrder(orderid, variety)` | Regular orders have no OCO. When one exit fills, cancel the other at once. If both filled in a fast move, you're now positioned the other way, so flatten immediately. |
| Time exit | 15:15 | `cancelOrder` x2, then `placeOrderFullResponse` | `exit_now()`: opposite side `INTRADAY LIMIT` at LTP -/+ 0.5% |

Exits always use the **printed** stop and T1, not levels recomputed from your fill: the backtest does the same.

## 4. SDK behaviour that matters (from the 1.5.5 source)

1. **`placeOrder()` returns `None` on a rejection; it doesn't raise.** Use `placeOrderFullResponse()` and check
   `status` plus `data.orderid` / `data.uniqueorderid` yourself.
2. **A placed order is not a filled order.** Confirm the fill (`orderBook`, `individual_order_details`) before placing
   exits, and size the exits to the *filled* quantity.
3. **Never auto-retry a placement call.** The SDK has no idempotency key: a timeout after the request reached Angel One
   would place a duplicate. On any error, read the order book before doing anything else.
4. **`gttCreateRule()` raises `KeyError`** when the rule is rejected (it reads `['data']['id']` unconditionally).
5. **The SDK writes `logs/<date>/app.log` in the working directory** as soon as `SmartConnect` is created, and on a network
   error it logs the request **headers, including `Authorization: Bearer <JWT>`**. That's how session tokens ended up committed
   in both old repos. `logs/` is now in `.gitignore`; an executor should also keep that folder outside OneDrive and git.
6. `placeOrder` deletes `None` keys from the dict you pass in (it mutates it). Build a fresh body for every call.
7. `tradingsymbol` / `symboltoken` must be the **NSE** row of the scrip master. The same name exists on BSE and F&O, so
   `instrument()` filters on `exch_seg == "NSE"` and refuses zero or multiple matches.
8. Prices must sit on the tick grid. `instrument()` reads `tick_size` from the scrip master, and every price is rounded
   in the direction that keeps the order fillable.

## 5. Check on a 1-share live test before trusting it (not verifiable from here)

| Assumption | Why it matters |
|---|---|
| Scrip master `tick_size` is in paise (`"5.000000"` = Rs 0.05) | Wrong units = every order rejected |
| A `STOPLOSS_LIMIT` with the limit 2% beyond the trigger is accepted | Some brokers cap that distance; if so, shrink `STOP_LIMIT_BUFFER` |
| A SELL GTT on DELIVERY triggers when LTP *falls to* the stop as well as when it *rises to* T1 | Direction semantics decide whether the stop leg works at all |
| A SELL GTT is allowed on shares bought today (T1 holdings), and **DDPI/POA or eDIS** is active | Without it, a triggered GTT sell of demat shares is rejected, so the stop silently doesn't work |
| A GTT whose limit isn't reached (e.g. a gap down more than 2% below the stop) stays open | Then the daily check must sell it at market. The backtest sold at the open. |
| Optional `ordertag` length/charset (believed <= 20 chars) | Lets an executor find its own orders in the order book |

## 6. Not built yet: a live executor needs all of these

- Credentials from environment variables or a gitignored `.env`; never in code, logs, chat or git. Session via
  `generateSession(client_code, pin, totp)`; the TOTP secret is the most sensitive of the four.
- **Dry-run by default.** It prints the ticket bodies; a separate `--live` flag sends them. Start with 1 share.
- The verdict gate stays in `swing_ticket` / `intraday_ticket`: no validated Buy / setup, no order.
- Hard limits outside the strategy: risk per trade <= 1% (`position_size`), max open positions, a daily loss limit
  (intraday 3R), and a kill switch that cancels everything and flattens.
- Fill confirmation, the OCO checks and the time exits from §2 and §3; order-book reconciliation after every error.
- A run log without headers or tokens.
- It must run on a personal machine and network: Angel One is blocked on the Walmart network.
