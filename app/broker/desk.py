"""Order desk: turn the app's validated plan into a ticket, and record it. DRY RUN ONLY.

Nothing here talks to a broker. "Placing" an order writes the exact Angel One request bodies to a local journal,
so you can read, rehearse and audit them. Sending them is a separate, deliberate step (docs/ANGELONE_ORDERS.md, section 6:
credentials from the environment, 1-share test, order-book reconciliation, kill switch).

The browser never supplies order bodies. It sends symbol, mode, capital, risk and (optionally) a smaller quantity;
the ticket is rebuilt here from the server's own plan, so a doctored form cannot change a price, a side or a size.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app import data
from app.broker.angelone import Instrument, Ticket, instrument, intraday_ticket, position_size, swing_ticket

BROKER_DIR = data.DB_PATH.parent / "broker"
JOURNAL = BROKER_DIR / "orders.jsonl"
SCRIP_MASTER = BROKER_DIR / "scrip_master.json"   # Angel One's public OpenAPIScripMaster.json, downloaded on a personal network
MAX_RISK_PCT = 1.0                                # docs/ANGELONE_ORDERS.md section 6: risk per trade <= 1%
PLACEHOLDER_TICK = Decimal("0.05")
MODES = ("swing", "intraday")


class OrderRefused(Exception):
    """The desk will not record this order; the message says why."""


@dataclass(frozen=True)
class Draft:
    mode: str
    symbol: str
    ticket: Ticket
    inst: Instrument
    instrument_verified: bool
    qty: int
    max_qty: int
    ref_price: float
    ref_label: str
    stop: float
    risk_pct: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def can_place(self) -> bool:
        return self.ticket.entry is not None

    @property
    def side(self) -> str:
        return self.ticket.entry["transactiontype"] if self.ticket.entry else ""

    @property
    def rupees_at_risk(self) -> float:
        return 0.0 if not self.can_place else self.qty * abs(self.ref_price - self.stop)


# ---------- instrument lookup ----------

_scrip_memo: tuple[float, list[dict]] | None = None


def _scrip_master() -> list[dict] | None:
    global _scrip_memo
    if not SCRIP_MASTER.exists():
        return None
    stamp = SCRIP_MASTER.stat().st_mtime
    if _scrip_memo is None or _scrip_memo[0] != stamp:
        _scrip_memo = (stamp, json.loads(SCRIP_MASTER.read_text()))
    return _scrip_memo[1]


def load_instrument(symbol: str) -> tuple[Instrument, bool, str]:
    """(instrument, verified, note). Without the scrip master the token is a placeholder: fine for a dry run, never for a live order."""
    rows = _scrip_master()
    if rows is None:
        note = f"Scrip master not found at {SCRIP_MASTER.name}: the token below is a placeholder (dry run only)."
    else:
        try:
            return instrument(rows, symbol), True, ""
        except (LookupError, ValueError) as exc:
            note = f"Scrip master lookup failed ({exc}): the token below is a placeholder."
    return Instrument(symbol.removesuffix(".NS") + "-EQ", "UNKNOWN", PLACEHOLDER_TICK), False, note


# ---------- reference prices ----------

def swing_reference(symbol: str) -> tuple[float, str]:
    """Today's open is what the swing rule enters on; before the session opens, the latest daily bar is the best stand-in."""
    frame = data.load_ohlcv(symbol)
    if frame is None or frame.empty:
        return float("nan"), "no daily prices"
    return float(frame["Open"].iloc[-1]), f"open of the {frame.index[-1]:%d %b %Y} session"


def intraday_reference(report) -> tuple[float, str]:
    bar = report.snapshot.day.index[-1]
    return report.snapshot.price, f"close of the {bar:%H:%M} 5-minute bar"


# ---------- drafting ----------

def build_draft(mode: str, symbol: str, report, ref: tuple[float, str], capital: float, risk_pct: float,
                qty: int | None = None, inst: tuple[Instrument, bool, str] | None = None) -> Draft:
    """`report` is the StockReport (swing) or IntradayReport (intraday). qty may only shrink the sized quantity."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    notes = []
    ref_price, ref_label = ref
    risk = min(max(risk_pct, 0.0), MAX_RISK_PCT)
    if risk < risk_pct:
        notes.append(f"Risk capped at {MAX_RISK_PCT:g}% per trade (you asked for {risk_pct:g}%).")
    plan = report.plan if mode == "swing" else (report.best.plan if report.best else None)
    stop = plan.stop if plan else ref_price
    max_qty = position_size(capital, risk, ref_price, stop) if ref_price == ref_price else 0
    final_qty = max_qty if qty is None else max(1, min(qty, max_qty)) if max_qty else 0
    if qty is not None and qty > max_qty:
        notes.append(f"Quantity limited to {max_qty}: more would break the {risk:g}% risk rule or exceed your capital.")
    chosen = inst or load_instrument(symbol)
    instrument_, verified, inst_note = chosen
    if inst_note:
        notes.append(inst_note)
    ticket = (swing_ticket if mode == "swing" else intraday_ticket)(report, instrument_, final_qty, ref_price)
    return Draft(mode, symbol, ticket, instrument_, verified, final_qty, max_qty, ref_price, ref_label, stop, risk,
                 tuple(notes))


# ---------- journal ----------

def _read_journal() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(line) for line in JOURNAL.read_text().splitlines() if line.strip()]


def recent_orders(limit: int = 10) -> list[dict]:
    return _read_journal()[::-1][:limit]


def record(draft: Draft, now: datetime) -> dict:
    """Append the ticket to the journal (dry run). One order per mode, symbol and day: never a silent duplicate."""
    if not draft.can_place:
        raise OrderRefused(draft.ticket.skip or "nothing to place")
    key = f"{draft.mode}:{draft.symbol}:{now:%Y-%m-%d}"
    existing = _read_journal()
    if any(row["key"] == key for row in existing):
        raise OrderRefused(f"A {draft.mode} order for {draft.symbol} is already recorded today. "
                           "The desk never repeats an order: check the journal first.")
    row = {"id": len(existing) + 1, "key": key, "at": now.isoformat(timespec="seconds"), "dry_run": True,
           "mode": draft.mode, "symbol": draft.symbol, "qty": draft.qty, "side": draft.side,
           "instrument_verified": draft.instrument_verified, "entry": draft.ticket.entry,
           "exits": list(draft.ticket.exits), "time_exit": draft.ticket.time_exit}
    BROKER_DIR.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a") as handle:
        handle.write(json.dumps(row) + "\n")
    return row
