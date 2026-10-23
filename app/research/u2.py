"""U2: the independent universe of Addendum A (docs/SWING_RESEARCH_PLAN.md), frozen on 2026-10-23.

The candidate list below is FIXED. Names already in app.universe.STOCKS are removed in code. Bars live in
data/research/extra_history/ (git-ignored), never in the app's own cache, and only ever grow (data.top_up).
"""

import os
import time
from pathlib import Path

import pandas as pd

from app import data
from app.universe import STOCKS

CANDIDATES = """
ABB ACC ADANIGREEN ADANIPOWER ALKEM AMBUJACEM APLAPOLLO ASHOKLEY ASTRAL AUROPHARMA BALKRISIND BANDHANBNK
BANKBARODA BANKINDIA BERGEPAINT BHARATFORG BHEL BIOCON BOSCHLTD CANBK CGPOWER CHOLAFIN COFORGE COLPAL CONCOR
CUMMINSIND DABUR DALBHARAT DEEPAKNTR DIVISLAB DIXON ESCORTS EXIDEIND FEDERALBNK GLENMARK GODREJCP GODREJPROP
GUJGASLTD HAVELLS HINDPETRO HINDZINC ICICIGI ICICIPRULI IDFCFIRSTB IGL INDHOTEL INDIANB INDUSTOWER IRCTC
JINDALSTEL JUBLFOOD KPITTECH LICHSGFIN LODHA LTIM LTTS LUPIN M&MFIN MARICO MFSL MOTHERSON MPHASIS MRF
MUTHOOTFIN NAUKRI NAVINFLUOR NHPC NMDC OBEROIRLTY OFSS PAGEIND PERSISTENT PETRONET PFC PIIND PNB POLYCAB
PRESTIGE RECLTD SAIL SBICARD SHREECEM SRF SUNTV SUPREMEIND TATACHEM TATACOMM TATAELXSI TATAPOWER TIINDIA
TORNTPHARM TORNTPOWER UBL UNITDSPR UPL VOLTAS YESBANK ZYDUSLIFE ABCAPITAL AARTIIND ATUL AUBANK BATAINDIA
CROMPTON CUB EMAMILTD GRANULES HINDCOPPER IDEA IEX IPCALAB JKCEMENT JSWENERGY KAJARIACER LAURUSLABS
MANAPPURAM METROPOLIS NATIONALUM NBCC OIL RAMCOCEM RBLBANK SYNGENE THERMAX TRIDENT ZEEL CHAMBLFERT
COROMANDEL SUNDARMFIN HDFCAMC CRISIL CANFINHOME BSOFT CYIENT ELGIEQUIP KEI LALPATHLAB APOLLOTYRE CEATLTD
SCHAEFFLER SKFINDIA GILLETTE HONAUR 3MINDIA WHIRLPOOL ENDURANCE GSPL MGL AIAENG CESC NLCINDIA SJVN HUDCO
BEML COCHINSHIP FORTIS AJANTPHARM NATCOPHARM GLAXO PFIZER ABBOTINDIA SANOFI
""".split()
SYMBOLS = sorted({f"{c}.NS" for c in CANDIDATES} - set(STOCKS))
OUT = data.DB_PATH.parent / "research" / "extra_history"
BATCH, PAUSE, ATTEMPTS = 20, 5, 3


def path(symbol: str) -> Path:
    return OUT / f"{symbol.replace('&', '_')}.csv.gz"


def load(symbol: str) -> pd.DataFrame | None:
    p = path(symbol)
    return pd.read_csv(p, index_col=0, parse_dates=True) if p.exists() else None


def _save(symbol: str, frame: pd.DataFrame) -> None:
    tmp = path(symbol).with_suffix(".tmp.gz")
    frame.to_csv(tmp)
    os.replace(tmp, path(symbol))          # never a half-written series


def refresh(progress: data.Progress = data._no_progress) -> list[str]:
    """Top up every U2 series (first run: 10 years). Returns the symbols Yahoo did not return."""
    OUT.mkdir(parents=True, exist_ok=True)
    session, updated = data._fresh_session(), set()
    batches = [SYMBOLS[i: i + BATCH] for i in range(0, len(SYMBOLS), BATCH)]
    for n, batch in enumerate(batches, start=1):
        stored = {s: load(s) for s in batch}
        for attempt in range(ATTEMPTS):
            if merged := data.top_up(stored, session):
                break
            time.sleep(PAUSE * (attempt + 2))        # Yahoo rate-limits the shared proxy (HTTP 429)
        for symbol, frame in merged.items():
            _save(symbol, frame)
        updated |= set(merged)
        progress(n, len(batches), f"U2 prices, batch {n}")
        time.sleep(PAUSE if n < len(batches) else 0)
    if not updated:
        raise data.RefreshError("Could not download any U2 prices from Yahoo Finance. Check VPN/proxy.")
    return sorted(set(SYMBOLS) - updated)
