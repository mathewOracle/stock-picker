"""Fundamental-analysis pillar for coins: tokenomics, liquidity, track record and cycle position.

A coin has no earnings, balance sheet or cash flow, so P/E-style checks don't exist. What does exist:

* Size: market cap (deep markets, institutional access, harder to manipulate).
* Liquidity: 3-month average dollar volume / market cap. Too low = illiquid; too high = churn or wash trading.
* Dilution overhang: fully diluted value / market cap. Locked tokens that will unlock are future sell pressure.
* Supply cap: a coded maximum supply vs open-ended issuance.
* Measured supply inflation: from our own daily snapshots of circulating supply (needs 30+ days).
* Track record: years since launch (has it survived a full boom-bust cycle?).
* Cycle position: distance from the all-time high.
* Utility claim: meme coins are priced on attention, not usage.

Data: Yahoo Finance (sourced from CoinMarketCap). On-chain activity, developer activity and token unlock
schedules are NOT available from free sources here, so they are not scored (the coin page says so).
"""

import math
from datetime import date, datetime, timezone

from app.market.crypto import MEME
from app.prices import price_text
from app.signals import Signal, grade

NAN = float("nan")
YEAR_SECONDS = 365.25 * 86_400
MIN_SUPPLY_DAYS = 30            # fewer days of snapshots than this and annualised inflation is noise
HEAVY_DILUTION = 3.0            # FDV more than 3x the market cap: most tokens are still locked
ILLIQUID_TURNOVER = 0.005       # trading under 0.5% of the market cap a day
YOUNG_YEARS = 2.0
HARD_FLAGS = frozenset({"Falling knife", "Heavy dilution", "Illiquid", "Coarse price data"})   # these veto any buy
PILLAR_WEIGHTS = {"fundamental": 0.30, "technical": 0.40, "chart": 0.30}  # coins trend harder than they "value"


def _num(value) -> float:
    """A finite number, or NaN for missing / junk."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return NAN
    return number if math.isfinite(number) else NAN


def _positive(value) -> float:
    """Prices and supplies: zero means 'unknown' (Yahoo reports SHIB's all-time low as 0.0), not free."""
    number = _num(value)
    return number if number > 0 else NAN


def _ok(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def _div(a: float, b: float) -> float:
    return a / b if _ok(a, b) and b > 0 else NAN


def supply_growth(points: dict[str, float], min_days: int = MIN_SUPPLY_DAYS) -> tuple[float, int]:
    """(annualised circulating-supply growth, days observed) from {'YYYY-MM-DD': supply}. NaN until min_days."""
    usable = sorted((date.fromisoformat(d), s) for d, s in points.items() if _ok(_num(s)) and _num(s) > 0)
    if len(usable) < 2:
        return NAN, 0
    (first_day, first), (last_day, last) = usable[0], usable[-1]
    days = (last_day - first_day).days
    if days < min_days:
        return NAN, days
    return (last / first) ** (365 / days) - 1, days


def _age_years(info: dict, now: datetime) -> float:
    start = _num(info.get("startDate"))   # launch (unix seconds); Yahoo's first trade date is the fallback
    if not _ok(start):
        start = _num(info.get("firstTradeDateMilliseconds")) / 1000
    return (now.timestamp() - start) / YEAR_SECONDS if _ok(start) and start > 0 else NAN


def coin_metrics(info: dict, price: float, supply: dict[str, float] | None = None,
                 now: datetime | None = None) -> dict:
    """Every tokenomics number for one coin. Missing data comes back as NaN / None, never as a guess."""
    now = now or datetime.now(timezone.utc)
    cap, fdv = _num(info.get("marketCap")), _num(info.get("fullyDilutedValue"))
    circulating, total, max_supply = (_num(info.get(k)) for k in ("circulatingSupply", "totalSupply", "maxSupply"))
    has_cap = _ok(max_supply) and max_supply > 0
    ceiling = max_supply if has_cap else total
    ath, atl = _positive(info.get("allTimeHigh")), _positive(info.get("allTimeLow"))
    inflation, supply_days = supply_growth(supply or {})
    return {
        "market_cap": cap,
        "fdv": fdv,
        "fdv_ratio": _div(fdv, cap),
        "circulating": circulating,
        "total_supply": total,
        "max_supply": max_supply if has_cap else NAN,
        "has_cap": has_cap,
        "unlocked": min(_div(circulating, ceiling), 1.0) if _ok(_div(circulating, ceiling)) else NAN,
        "volume_24h": _num(info.get("volume24Hr")),
        "turnover": _div(_num(info.get("averageDailyVolume3Month")), cap),
        "ath": ath,
        "atl": atl,
        "off_ath": _div(price, ath) - 1 if _ok(_div(price, ath)) else NAN,
        "x_from_atl": _div(price, atl),
        "age_years": _age_years(info, now),
        "inflation": inflation,
        "supply_days": supply_days,
    }


def _big(value: float) -> str:
    for size, label in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= size:
            return f"{value / size:,.1f}{label}"
    return f"{value:,.0f}"


# ---------- checks ----------

def _size(m: dict) -> Signal | None:
    cap = m["market_cap"]
    if not _ok(cap):
        return None
    pts = grade(cap, [(100e9, 1.0), (10e9, 0.5), (1e9, 0.0)], below=-0.7)
    note = {1.0: "Blue chip: deep markets and institutional access, hard to push around.",
            0.5: "Large cap: established, still far more volatile than Bitcoin.",
            0.0: "Mid cap: thinner markets, bigger swings."}.get(pts, "Small cap: thin markets that a few wallets can move.")
    return Signal("Network size (market cap)", f"${_big(cap)}", pts, 1.5, note)


def _liquidity(m: dict) -> Signal | None:
    turnover = m["turnover"]
    if not _ok(turnover):
        return None
    if turnover < ILLIQUID_TURNOVER:
        pts, note = -1.0, "Illiquid: exits get expensive exactly when everyone wants out."
    elif turnover < 0.01:
        pts, note = -0.3, "Light trading for its size."
    elif turnover <= 0.15:
        pts, note = 1.0, "Healthy turnover: easy to enter and exit."
    elif turnover <= 0.30:
        pts, note = 0.0, "Very heavy trading: speculative churn dominates."
    else:
        pts, note = -0.5, "Trades more than holders plausibly would: a frenzy or wash trading."
    return Signal("Liquidity (3M avg volume / market cap)", f"{turnover:.1%} a day", pts, 1.5, note)


def _dilution(m: dict) -> Signal | None:
    ratio = m["fdv_ratio"]
    if not _ok(ratio):
        return None
    pts = grade(-ratio, [(-1.1, 1.0), (-1.5, 0.3), (-HEAVY_DILUTION, -0.5)], below=-1.0)
    circulating = f", {m['unlocked']:.0%} of supply circulating" if _ok(m["unlocked"]) else ""
    note = {1.0: "Almost all supply already trades: little dilution ahead.",
            0.3: "Some supply still to come: modest dilution ahead.",
            -0.5: "Large unlocks ahead: new supply will compete with demand."}.get(
        pts, "Most tokens are still locked: unlocks are a persistent sell pressure.")
    return Signal("Dilution overhang (FDV / market cap)", f"{ratio:.2f}x{circulating}", pts, 2.0, note)


def _supply_cap(m: dict) -> Signal:
    if m["has_cap"]:
        return Signal("Supply cap", f"max {_big(m['max_supply'])} coins", 0.5, 1.0,
                      "Fixed maximum supply: scarcity is written into the protocol.")
    return Signal("Supply cap", "no maximum supply", -0.3, 1.0,
                  "Open-ended supply: scarcity depends on the issuance and burn policy.")


def _inflation(m: dict) -> Signal:
    rate, days = m["inflation"], m["supply_days"]
    if not _ok(rate):
        return Signal("Supply inflation (measured)", f"collecting data ({days} of {MIN_SUPPLY_DAYS} days)", 0.0, 0.0,
                      "Measured from daily snapshots of circulating supply; scored once a month of data exists.")
    if rate < 0:
        pts, note = 1.0, "Supply is shrinking: burns exceed issuance."
    else:
        pts = grade(-rate, [(-0.01, 1.0), (-0.05, 0.3), (-0.15, -0.5)], below=-1.0)
        note = {1.0: "Supply barely growing.", 0.3: "Modest issuance.",
                -0.5: "Meaningful issuance dilutes holders."}.get(pts, "Heavy issuance: price must rise just to stand still.")
    return Signal("Supply inflation (measured)", f"{rate:+.1%} a year over {days} days", pts, 1.5, note)


def _track_record(m: dict) -> Signal | None:
    years = m["age_years"]
    if not _ok(years):
        return None
    pts = grade(years, [(8, 1.0), (4, 0.5), (YOUNG_YEARS, 0.0)], below=-0.7)
    note = {1.0: "Has survived several boom-bust cycles.", 0.5: "Has been through at least one full cycle.",
            0.0: "Some history, but not a full cycle."}.get(pts, "Young: no full bear market behind it yet.")
    return Signal("Track record (age)", f"{years:.1f} years", pts, 1.0, note)


def _cycle(m: dict) -> Signal | None:
    off = m["off_ath"]
    if not _ok(off):
        return None
    pts = grade(off, [(-0.25, 0.5), (-0.60, 0.0), (-0.85, -0.5)], below=-1.0)
    note = {0.5: "Near its highs: demand is intact.", 0.0: "Mid-cycle drawdown.",
            -0.5: "Deep drawdown: much of the market has given up on it."}.get(
        pts, "Down more than 85%: most coins this far down never get back.")
    return Signal("Distance from all-time high", f"{off:.0%} (ATH ${price_text(m['ath'], 2, 4)})", pts, 1.0, note)


def _utility(category: str) -> Signal | None:
    if category != MEME:
        return None
    return Signal("Utility claim", "meme coin", -0.5, 1.0, "Priced on attention and community, not usage or fees.")


def analyze_tokenomics(m: dict, category: str) -> list[Signal]:
    checks = (_size(m), _liquidity(m), _dilution(m), _supply_cap(m) if _ok(m["market_cap"]) else None,
              _inflation(m), _track_record(m), _cycle(m), _utility(category))
    return [s for s in checks if s is not None]


def tokenomic_flags(m: dict, category: str) -> list[str]:
    """Warnings; those in HARD_FLAGS veto a buy."""
    out = []
    if _ok(m["fdv_ratio"]) and m["fdv_ratio"] > HEAVY_DILUTION:
        out.append("Heavy dilution")
    if _ok(m["turnover"]) and m["turnover"] < ILLIQUID_TURNOVER:
        out.append("Illiquid")
    if category == MEME:
        out.append("Meme coin")
    if _ok(m["age_years"]) and m["age_years"] < YOUNG_YEARS:
        out.append("Young coin (< 2 yrs)")
    if _ok(m["off_ath"]) and m["off_ath"] < -0.85:
        out.append("Down > 85% from ATH")
    return out
