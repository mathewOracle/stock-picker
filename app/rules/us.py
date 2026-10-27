"""US trading rules, as pure functions. Callers pass the calendar, the journal and the clock; nothing here does I/O.

What each rule means for this app (sources: the rule texts; re-check yearly, numbers and proposals change):

* FINRA Rule 4210(f)(8)(B), pattern day trader: in a MARGIN account, 4+ day trades within 5 business days makes you a
  PDT, and a PDT must keep $25,000 equity or day trading is frozen. Every intraday ticket is a day trade (it is
  flat by the square-off), so the desk counts them from its journal and refuses the 4th under $25k. FINRA has
  proposed replacing the $25k minimum with intraday margin rules: until your broker changes policy, it applies.
* Reg SHO Rule 201, short-sale circuit breaker: once a stock trades 10% below the prior close, short sales may only
  be priced ABOVE the national best bid for the rest of that day and the whole next day. Our short entries are
  marketable limits (they cross the spread), so they are refused while it is active, live AND in the backtest.
* Reg SHO Rule 203(b) (locate) and Rule 200(g) (order marking): a short needs a borrow located first and the order
  marked "sell short"; borrow fees apply. Shorts also need a margin account (Reg T: short sales are margin trades,
  150% requirement = 100% proceeds + 50% initial).
* SEC Rule 15c6-1, T+1 settlement (since 28 May 2024). In a CASH account, buying with unsettled proceeds and
  selling before they settle is a good-faith violation; brokers restrict the account after repeats (Reg T 220.8).
* Reg NMS Rule 612 (sub-penny rule): orders priced at $1.00 or more must be in whole cents; below $1, $0.0001.
* IRS section 1091, wash sale: a loss is disallowed if substantially identical stock is bought within 30 days
  before or after the losing sale; it moves into the new position's cost basis.
* Holding period: one year or less = short-term capital gain, taxed as ordinary income. Every app trade is short-term.
* LULD (Limit Up-Limit Down) pauses and market-wide circuit breakers: no stop can fill during a halt; it fills at
  the reopen price, which can be far past the stop.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from app.rules import Check, DeskContext

PDT_EQUITY_MIN = 25_000
PDT_MAX_DAY_TRADES = 3        # a 4th within the window makes a pattern day trader
PDT_WINDOW_SESSIONS = 5
RULE201_DROP = 0.10
WASH_SALE_DAYS = 30
CENT, SUBPENNY = Decimal("0.01"), Decimal("0.0001")
RULE201_BLOCK = ("Reg SHO Rule 201 is active (the stock fell 10% below a prior close): short sales must be priced above "
                 "the national best bid, so a marketable short entry is not allowed")

IsSession = Callable[[date], bool]


def _market_is_session(day: date) -> bool:
    from app.market.us import MARKET as US
    return US.session(day) is not None


# ---------- calendar ----------

def recent_sessions(today: date, n: int, is_session: IsSession = _market_is_session) -> list[date]:
    """The last `n` sessions ending today (today included if it is a session), oldest first."""
    out, day = [], today
    while len(out) < n:
        if is_session(day):
            out.append(day)
        day -= timedelta(days=1)
    return out[::-1]


def settlement_date(trade_day: date, is_session: IsSession = _market_is_session) -> date:
    """T+1: the next session after the trade date."""
    day = trade_day + timedelta(days=1)
    while not is_session(day):
        day += timedelta(days=1)
    return day


# ---------- prices ----------

def tick_for(price: float) -> Decimal:
    """Rule 612: whole cents at $1.00 and above, $0.0001 below (a cent price is always valid either way)."""
    return CENT if price >= 1 else SUBPENNY


# ---------- Reg SHO Rule 201 ----------

def rule201_triggered(low: float, prev_close: float) -> bool:
    return prev_close > 0 and low <= prev_close * (1 - RULE201_DROP)


def rule201_active(bars: pd.DataFrame) -> bool:
    """Intraday bars over several sessions, ending NOW. Active if triggered today so far, or on the previous session.

    Uses each session's last 5-minute close as its close (Yahoo's bars; the official closing print can differ by a
    few cents, which only matters for a stock sitting exactly on the 10% line).
    """
    if bars is None or bars.empty:
        return False
    days = bars.groupby(bars.index.date).agg(low=("Low", "min"), close=("Close", "last"))
    if len(days) < 2:
        return False
    today = rule201_triggered(days["low"].iloc[-1], days["close"].iloc[-2])
    yesterday = len(days) >= 3 and rule201_triggered(days["low"].iloc[-2], days["close"].iloc[-3])
    return bool(today or yesterday)


# ---------- journal-based rules ----------

def _day(row: dict) -> date:
    return datetime.fromisoformat(row["at"]).date()


def day_trades(journal: tuple[dict, ...], today: date, is_session: IsSession = _market_is_session) -> int:
    """Margin-account day trades in the PDT window ending today. Every intraday order is one (flat by square-off).

    Rows recorded before the account field existed count as margin: overcounting is the safe side.
    """
    window = set(recent_sessions(today, PDT_WINDOW_SESSIONS, is_session))
    return sum(1 for r in journal if r.get("mode") == "intraday" and r.get("account", "margin") == "margin"
               and _day(r) in window)


def bought_today_cash(journal: tuple[dict, ...], today: date) -> float:
    """Settled cash already committed today in the cash account (proceeds of today's sales settle tomorrow)."""
    return sum(float(r.get("notional", 0.0)) for r in journal if r.get("account") == "cash" and _day(r) == today)


def recent_same_symbol(journal: tuple[dict, ...], symbol: str, today: date) -> dict | None:
    cutoff = today - timedelta(days=WASH_SALE_DAYS)
    rows = [r for r in journal if r.get("symbol") == symbol and cutoff <= _day(r) <= today]
    return rows[-1] if rows else None


# ---------- the checks ----------

def _money(value: float) -> str:
    return f"${value:,.0f}"


def pdt_check(ctx: DeskContext, is_session: IsSession) -> Check:
    rule = "FINRA Rule 4210 (pattern day trader)"
    if ctx.capital >= PDT_EQUITY_MIN:
        return Check(rule, "ok", f"Equity {_money(ctx.capital)} is at least {_money(PDT_EQUITY_MIN)}: day trades are not limited.")
    used = day_trades(ctx.journal, ctx.now.date(), is_session)
    if used >= PDT_MAX_DAY_TRADES:
        return Check(rule, "block", f"This would be day trade {used + 1} in {PDT_WINDOW_SESSIONS} sessions with equity under "
                                    f"{_money(PDT_EQUITY_MIN)}: you would be flagged a pattern day trader and day trading "
                                    "frozen. Wait for an older day trade to leave the window, or trade swing.")
    return Check(rule, "warn" if used == PDT_MAX_DAY_TRADES - 1 else "ok",
                 f"Day trade {used + 1} of {PDT_MAX_DAY_TRADES} allowed in {PDT_WINDOW_SESSIONS} sessions under "
                 f"{_money(PDT_EQUITY_MIN)} equity (counted from this desk's journal only: add any made elsewhere).")


def short_checks(ctx: DeskContext) -> list[Check]:
    if ctx.account == "cash":
        return [Check("Reg T (short sales need margin)", "block",
                      "Short selling is only possible in a margin account. Switch the account type, or skip this setup.")]
    out = [Check("Reg SHO Rules 203(b) and 200(g) (locate, marking)", "warn",
                 "Your broker must locate shares to borrow before the short; the order is marked \"sell short\". "
                 "Check the stock shows as easy-to-borrow; borrow fees reduce the result."),
           Check("Reg T (short margin)", "info",
                 f"A short needs 150% margin: the {_money(ctx.notional)} proceeds stay with the broker plus "
                 f"{_money(ctx.notional / 2)} of your equity.")]
    if ctx.rule201:
        out.insert(0, Check("Reg SHO Rule 201 (short-sale circuit breaker)", "block", RULE201_BLOCK + "."))
    elif ctx.rule201 is None:
        out.insert(0, Check("Reg SHO Rule 201 (short-sale circuit breaker)", "warn",
                            "Couldn't check whether the circuit breaker is active: check your broker's SSR flag first."))
    return out


def cash_checks(ctx: DeskContext, is_session: IsSession) -> list[Check]:
    available = ctx.capital - bought_today_cash(ctx.journal, ctx.now.date())
    settles = settlement_date(ctx.now.date(), is_session)
    if ctx.notional > available:
        return [Check("Reg T 220.8 (good-faith violation)", "block",
                      f"Needs {_money(ctx.notional)} of settled cash but only {_money(max(available, 0))} is left today "
                      "after this desk's earlier buys. Buying with unsettled money and selling before it settles is a "
                      "good-faith violation; repeats restrict the account.")]
    note = (f"Paid with settled cash. Today's sale proceeds settle on {settles:%a %d %b}: don't use them for another "
            "round trip before then (good-faith violation)." if ctx.mode == "intraday"
            else f"Paid with settled cash; this buy settles on {settles:%a %d %b} (T+1).")
    return [Check("Reg T 220.8 (cash account)", "ok", note)]


def desk_checks(ctx: DeskContext, is_session: IsSession = _market_is_session) -> list[Check]:
    """Every US rule that bears on this order, worst first. The desk records it only if none blocks."""
    checks: list[Check] = []
    if ctx.symbol in ctx.restricted:
        checks.append(Check("Restricted list (insider-trading / employer pre-clearance policy)", "block",
                            f"{ctx.symbol} is on your restricted list (data-us/broker/restricted.txt)."))
    if ctx.direction < 0:
        checks += short_checks(ctx)
    if ctx.account == "cash":
        checks += cash_checks(ctx, is_session)
    elif ctx.mode == "intraday":
        checks.append(pdt_check(ctx, is_session))
    if ctx.account == "margin":
        checks.append(Check("SEC Rule 15c6-1 (T+1 settlement)", "info",
                            f"Trades today settle on {settlement_date(ctx.now.date(), is_session):%a %d %b}."))
    if (earlier := recent_same_symbol(ctx.journal, ctx.symbol, ctx.now.date())) is not None:
        checks.append(Check("IRS section 1091 (wash sale)", "warn",
                            f"You traded {ctx.symbol} on {_day(earlier):%d %b}. If that trade closed at a loss, buying again "
                            f"within {WASH_SALE_DAYS} days defers the loss into this position's cost basis."))
    if ctx.mode == "swing" and ctx.earnings is not None:
        last_day = ctx.now.date() + timedelta(days=ctx.hold_sessions * 7 // 5 + 1)
        if ctx.now.date() <= ctx.earnings <= last_day:
            checks.append(Check("Earnings inside the hold", "warn",
                                f"Earnings on {ctx.earnings:%d %b} fall inside the {ctx.hold_sessions}-session hold: "
                                "the price can gap straight through the stop."))
    checks.append(Check("Holding period (tax)", "info",
                        "Held one year or less: any gain is short-term and taxed as ordinary income."))
    if ctx.mode == "intraday":
        checks.append(Check("LULD pauses / market-wide circuit breakers", "info",
                            "During a trading halt no stop can fill; it fills at the reopen price, which can be far past the stop."))
    order = {"block": 0, "warn": 1, "ok": 2, "info": 3}
    return sorted(checks, key=lambda c: order[c.status])
