"""Download 10 years of daily bars for Addendum A's independent universe (docs/SWING_RESEARCH_PLAN.md).

The candidate list below is FIXED (committed before any download). Names already in app.universe.STOCKS are
removed in code. Bars go to data/research/extra_history/ (git-ignored), never into the app's own cache.

Needs the corporate proxy:  HTTPS_PROXY=http://sysproxy.wal-mart.com:8080 .venv/bin/python -m scripts.fetch_extra_universe
"""

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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [s for s in SYMBOLS if not path(s).exists()]
    print(f"{len(SYMBOLS)} candidates outside the app universe; {len(todo)} still to download")
    for i in range(0, len(todo), BATCH):
        batch = todo[i: i + BATCH]
        for attempt in range(ATTEMPTS):
            frames = data._download(batch, data._fresh_session(), period="10y")
            if frames:
                break
            time.sleep(PAUSE * (attempt + 2))        # Yahoo rate-limits the shared proxy (HTTP 429)
        for symbol, frame in frames.items():
            frame.to_csv(path(symbol))
        print(f"  batch {i // BATCH + 1}: {len(frames)}/{len(batch)} saved")
        time.sleep(PAUSE)
    have = [s for s in SYMBOLS if path(s).exists()]
    print(f"done: {len(have)} of {len(SYMBOLS)} stored; missing: {sorted(set(SYMBOLS) - set(have))}")


if __name__ == "__main__":
    main()
