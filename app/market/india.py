"""India: large/mega-cap NSE stocks (Nifty 50 + a few heavyweights), Angel One tickets, IST clock.

Symbols are Yahoo Finance tickers. Anything Yahoo can't resolve is skipped at refresh time, so a stale
entry here is harmless. The U2 list is FROZEN (docs/SWING_RESEARCH_PLAN.md, Addendum A, 2026-10-23).
"""

from datetime import time
from zoneinfo import ZoneInfo

from app.market.profile import Clock, Market, Money, News, Wording

STOCKS: dict[str, str] = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank",
    "ICICIBANK.NS": "ICICI Bank",
    "BHARTIARTL.NS": "Bharti Airtel",
    "INFY.NS": "Infosys",
    "SBIN.NS": "State Bank of India",
    "ITC.NS": "ITC",
    "HINDUNILVR.NS": "Hindustan Unilever",
    "LT.NS": "Larsen & Toubro",
    "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "AXISBANK.NS": "Axis Bank",
    "BAJFINANCE.NS": "Bajaj Finance",
    "MARUTI.NS": "Maruti Suzuki",
    "M&M.NS": "Mahindra & Mahindra",
    "SUNPHARMA.NS": "Sun Pharma",
    "HCLTECH.NS": "HCL Technologies",
    "NTPC.NS": "NTPC",
    "ULTRACEMCO.NS": "UltraTech Cement",
    "TITAN.NS": "Titan Company",
    "ASIANPAINT.NS": "Asian Paints",
    "POWERGRID.NS": "Power Grid",
    "ONGC.NS": "ONGC",
    "COALINDIA.NS": "Coal India",
    "TATASTEEL.NS": "Tata Steel",
    "JSWSTEEL.NS": "JSW Steel",
    "ADANIENT.NS": "Adani Enterprises",
    "ADANIPORTS.NS": "Adani Ports",
    "WIPRO.NS": "Wipro",
    "TECHM.NS": "Tech Mahindra",
    "NESTLEIND.NS": "Nestle India",
    "BAJAJFINSV.NS": "Bajaj Finserv",
    "HINDALCO.NS": "Hindalco",
    "GRASIM.NS": "Grasim",
    "CIPLA.NS": "Cipla",
    "DRREDDY.NS": "Dr. Reddy's",
    "EICHERMOT.NS": "Eicher Motors",
    "BAJAJ-AUTO.NS": "Bajaj Auto",
    "HEROMOTOCO.NS": "Hero MotoCorp",
    "APOLLOHOSP.NS": "Apollo Hospitals",
    "TATACONSUM.NS": "Tata Consumer",
    "SBILIFE.NS": "SBI Life",
    "HDFCLIFE.NS": "HDFC Life",
    "SHRIRAMFIN.NS": "Shriram Finance",
    "INDUSINDBK.NS": "IndusInd Bank",
    "BEL.NS": "Bharat Electronics",
    "TRENT.NS": "Trent",
    "ETERNAL.NS": "Eternal (Zomato)",
    "JIOFIN.NS": "Jio Financial",
    "TMPV.NS": "Tata Motors (PV)",
    "MAXHEALTH.NS": "Max Healthcare",
    "INDIGO.NS": "InterGlobe Aviation",
    "HAL.NS": "Hindustan Aeronautics",
    "DMART.NS": "Avenue Supermarts",
    "PIDILITIND.NS": "Pidilite",
    "SIEMENS.NS": "Siemens India",
    "TVSMOTOR.NS": "TVS Motor",
    "DLF.NS": "DLF",
    "LICI.NS": "LIC of India",
    "VEDL.NS": "Vedanta",
    "BPCL.NS": "BPCL",
    "IOC.NS": "Indian Oil",
    "GAIL.NS": "GAIL",
}

INDICES: dict[str, str] = {
    "^NSEI": "Nifty 50",
    "^BSESN": "Sensex",
    "^NSEBANK": "Nifty Bank",
    "^CNXIT": "Nifty IT",
    "^INDIAVIX": "India VIX",
    "INR=X": "USD/INR",
}

# Headline names that differ from the display name (or are ambiguous words).
NEWS_ALIASES: dict[str, tuple[str, ...]] = {
    "HINDUNILVR.NS": ("Hindustan Unilever", "HUL"), "LT.NS": ("Larsen & Toubro", "L&T"),
    "M&M.NS": ("Mahindra & Mahindra", "M&M"), "TITAN.NS": ("Titan Company", "Titan Co"),
    "ETERNAL.NS": ("Eternal", "Zomato"), "TMPV.NS": ("Tata Motors Passenger", "Tata Motors"),
    "DMART.NS": ("Avenue Supermarts", "DMart", "D-Mart"), "BEL.NS": ("Bharat Electronics",),
    "HAL.NS": ("Hindustan Aeronautics", "HAL"), "LICI.NS": ("Life Insurance Corporation", "LIC of India", "LIC"),
    "INDIGO.NS": ("IndiGo", "InterGlobe Aviation"), "IOC.NS": ("Indian Oil", "IOC"),
    "JIOFIN.NS": ("Jio Financial",), "SIEMENS.NS": ("Siemens India", "Siemens Ltd"),
    "TRENT.NS": ("Trent Ltd", "Trent share", "Tata Trent"), "ITC.NS": ("ITC Ltd", "ITC share", "ITC shares"),
    "NESTLEIND.NS": ("Nestle India",), "TCS.NS": ("Tata Consultancy Services", "TCS"),
    "VEDL.NS": ("Vedanta",), "SBILIFE.NS": ("SBI Life",), "HDFCLIFE.NS": ("HDFC Life",),
    "BAJAJ-AUTO.NS": ("Bajaj Auto",), "DRREDDY.NS": ("Dr Reddy's", "Dr. Reddy's"),
}

U2_CANDIDATES = """
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

MARKET = Market(
    key="india", app_name="Stock Picker", short_name="India", exchange="NSE", regulator="SEBI",
    clock=Clock(tz=ZoneInfo("Asia/Kolkata"), open=time(9, 15), close=time(15, 30),
                early_label="Pre-open auction", early_start=time(9, 0)),
    stocks=STOCKS, indices=INDICES, benchmark="^NSEI", benchmark_name="Nifty", vix="^INDIAVIX", vix_name="India VIX",
    money=Money("₹", 1e7, "Cr", locale="en-IN"),
    swing_cost_per_side=0.0015,     # brokerage + STT + stamp + slippage, deliberately conservative
    intraday_cost_per_side=0.0006,  # brokerage + STT + exchange fees + GST + stamp + slippage, NSE intraday, large caps
    min_traded_value=100,           # Rs crore/day: below this, spreads/impact costs eat intraday edges
    news=News(locale="hl=en-IN&gl=IN&ceid=IN:en", finance_terms="(shares OR stock OR results OR earnings OR NSE)",
              aliases=NEWS_ALIASES),
    u2_candidates=tuple(f"{c}.NS" for c in U2_CANDIDATES),
    broker_name="Angel One", symbol_suffix=".NS",
    wording=Wording(intraday_product="intraday (MIS) product", swing_product="the delivery (CNC) product",
                    swing_exit_order="a GTT OCO order (good-till-triggered, one-cancels-the-other)",
                    swing_exit_why="A plain stop-loss order expires every evening; a GTT doesn't.",
                    adviser="a SEBI-registered adviser", costs_detail="brokerage, STT, slippage",
                    forward_why=("Momentum was the only lead in all of this research (it passed 2017-21 on stocks outside "
                                 "this app's list, then fell short in 2022-24), and those backtests are flattered by "
                                 "survivorship bias."),
                    forward_rules="Addendum B of docs/SWING_RESEARCH_PLAN.md"),
)
