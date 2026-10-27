"""United States: large/mega-cap NYSE/Nasdaq stocks, S&P 500 benchmark, New York clock on the real NYSE calendar.

Regulatory checks (PDT, Reg SHO Rule 201, T+1, Reg T, Rule 612 ticks, wash sales) live in app/rules/us.py;
this module is data only. Symbols are Yahoo tickers (class B shares use a dash: BRK-B). Anything Yahoo can't
resolve is skipped at refresh time. The U2 list is FROZEN (docs/us/SWING_RESEARCH_PLAN.md, 2026-10-27).
"""

from dataclasses import dataclass
from datetime import date, time
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd

from app.market.profile import Clock, Market, Money, News, Session, Wording

NEW_YORK = ZoneInfo("America/New_York")

STOCKS: dict[str, str] = {
    # Technology
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AVGO": "Broadcom", "ORCL": "Oracle",
    "CRM": "Salesforce", "ADBE": "Adobe", "AMD": "AMD", "CSCO": "Cisco", "ACN": "Accenture",
    "INTC": "Intel", "QCOM": "Qualcomm", "TXN": "Texas Instruments", "IBM": "IBM",
    # Communication services
    "GOOGL": "Alphabet", "META": "Meta Platforms", "NFLX": "Netflix", "DIS": "Disney",
    "TMUS": "T-Mobile US", "VZ": "Verizon", "T": "AT&T",
    # Consumer cyclical
    "AMZN": "Amazon", "TSLA": "Tesla", "HD": "Home Depot", "MCD": "McDonald's", "NKE": "Nike",
    "LOW": "Lowe's", "SBUX": "Starbucks", "BKNG": "Booking Holdings",
    # Consumer defensive
    "WMT": "Walmart", "COST": "Costco", "PG": "Procter & Gamble", "KO": "Coca-Cola", "PEP": "PepsiCo",
    "PM": "Philip Morris", "MDLZ": "Mondelez", "CL": "Colgate-Palmolive",
    # Healthcare
    "LLY": "Eli Lilly", "UNH": "UnitedHealth", "JNJ": "Johnson & Johnson", "ABBV": "AbbVie", "MRK": "Merck",
    "TMO": "Thermo Fisher", "ABT": "Abbott", "PFE": "Pfizer", "AMGN": "Amgen", "ISRG": "Intuitive Surgical",
    # Financials
    "JPM": "JPMorgan Chase", "V": "Visa", "MA": "Mastercard", "BAC": "Bank of America", "WFC": "Wells Fargo",
    "GS": "Goldman Sachs", "MS": "Morgan Stanley", "AXP": "American Express", "BLK": "BlackRock",
    "BRK-B": "Berkshire Hathaway",
    # Industrials
    "GE": "GE Aerospace", "CAT": "Caterpillar", "HON": "Honeywell", "UNP": "Union Pacific", "RTX": "RTX",
    "BA": "Boeing", "DE": "Deere", "LMT": "Lockheed Martin", "UPS": "UPS",
    # Energy
    "XOM": "Exxon Mobil", "CVX": "Chevron", "COP": "ConocoPhillips",
    # Utilities
    "NEE": "NextEra Energy", "DUK": "Duke Energy", "SO": "Southern Company",
    # Real estate
    "PLD": "Prologis", "AMT": "American Tower", "EQIX": "Equinix",
    # Basic materials
    "LIN": "Linde", "SHW": "Sherwin-Williams", "FCX": "Freeport-McMoRan",
}

INDICES: dict[str, str] = {
    "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^DJI": "Dow Jones", "^RUT": "Russell 2000", "^VIX": "VIX",
}

# Headline names that differ from the display name, or display names that are ordinary words.
NEWS_ALIASES: dict[str, tuple[str, ...]] = {
    "GOOGL": ("Alphabet", "Google"), "META": ("Meta Platforms", "Meta"), "AMD": ("AMD", "Advanced Micro Devices"),
    "T": ("AT&T",), "V": ("Visa Inc", "Visa"), "MA": ("Mastercard",), "PG": ("Procter & Gamble", "P&G"),
    "JNJ": ("Johnson & Johnson", "J&J"), "GE": ("GE Aerospace", "General Electric"), "LLY": ("Eli Lilly", "Lilly"),
    "JPM": ("JPMorgan", "JPMorgan Chase"), "XOM": ("Exxon Mobil", "Exxon"), "BRK-B": ("Berkshire Hathaway", "Berkshire"),
    "TMUS": ("T-Mobile",), "RTX": ("RTX", "Raytheon"), "DE": ("Deere", "John Deere"), "UPS": ("UPS", "United Parcel"),
    "SO": ("Southern Company", "Southern Co"), "HD": ("Home Depot",), "LIN": ("Linde",), "BKNG": ("Booking Holdings",),
}

# U2: an independent universe for the forward test: S&P 500 names NOT in STOCKS. Frozen 2026-10-27.
U2_CANDIDATES = """
ADI AMAT LRCX KLAC MU INTU NOW PANW SNPS CDNS FTNT ANET MCHP NXPI ON HPQ DELL GLW TEL APH IT AKAM FFIV NTAP STX
WDC ZBRA TER SWKS EA TTWO CHTR CMCSA OMC WBD FOXA TJX ROST ORLY AZO CMG YUM DRI MAR HLT EBAY BBY TGT DG DLTR KR SYY
GIS HSY KMB CHD CLX KHC MO STZ TSN HRL MKC CAG F GM APTV LVS RCL CCL POOL TSCO ULTA LULU DECK NVR DHI LEN PHM BMY
GILD VRTX REGN BIIB MDT SYK BSX EW ZBH BDX BAX CI ELV HUM CVS MCK CAH COR IQV A DHR MTD WAT IDXX RMD DXCM HCA C SCHW
PNC USB TFC COF MMC AON CB PGR TRV ALL MET PRU AIG ICE CME SPGI MCO NDAQ BK STT TROW FITB KEY RF HBAN MTB SYF AFL
MMM ETN EMR ITW PH ROK GD NOC LHX CSX NSC FDX WM RSG CTAS PCAR CMI GWW FAST URI JCI CARR OTIS DOV XYL IR AME ROP
LUV DAL UAL SLB EOG PSX MPC VLO OXY KMI WMB OKE HAL DVN BKR FANG AEP D EXC SRE XEL PEG ED WEC ES PCG EIX DTE SPG
O PSA WELL DLR CCI AVB EQR VTR APD ECL NEM NUE DOW DD PPG VMC MLM IP BALL ALB CF MOS
""".split()


@lru_cache(maxsize=1)
def _nyse():
    """The NYSE calendar (holidays AND half-days), built once. Its default horizon is only a year, so extend it."""
    import exchange_calendars as xc
    return xc.get_calendar("XNYS", start="2014-01-01", end=(pd.Timestamp.today() + pd.DateOffset(years=2)).strftime("%Y-%m-%d"))


@dataclass(frozen=True)
class USMarket(Market):
    def session(self, day: date) -> Session | None:
        cal, ts = _nyse(), pd.Timestamp(day)
        if not cal.is_session(ts):
            return None
        hours = (cal.session_open(ts).tz_convert(NEW_YORK).time(), cal.session_close(ts).tz_convert(NEW_YORK).time())
        return Session(*hours)

    @property
    def knows_holidays(self) -> bool:
        return True


MARKET = USMarket(
    key="us", app_name="US Stock Picker", short_name="US", exchange="NYSE/Nasdaq", regulator="SEC/FINRA",
    clock=Clock(tz=NEW_YORK, open=time(9, 30), close=time(16, 0),
                early_label="Pre-market (extended hours)", early_start=time(4, 0),
                overnight_label="Closed (overnight)"),
    stocks=STOCKS, indices=INDICES, benchmark="^GSPC", benchmark_name="S&P 500", vix="^VIX", vix_name="VIX",
    money=Money("$", 1e6, "M", steps=((1e12, "T"), (1e9, "B"), (1e6, "M"))),
    # $0 commission at most US brokers; the cost is half-spread + slippage (~3-4 bp on mega caps at a 5-minute bar
    # open) plus the SEC Section 31 and FINRA TAF sell-side fees (< 0.3 bp combined). 5 bp a side is deliberately high.
    swing_cost_per_side=0.0005,
    intraday_cost_per_side=0.0005,
    min_traded_value=100,           # $M/day traded: below this, spreads/impact costs eat intraday edges
    news=News(locale="hl=en-US&gl=US&ceid=US:en", finance_terms="(shares OR stock OR earnings OR NYSE OR Nasdaq)",
              aliases=NEWS_ALIASES),
    u2_candidates=tuple(U2_CANDIDATES),
    broker_name="broker-neutral",
    wording=Wording(intraday_product="a regular-session day order (no extended hours)",
                    swing_product="a regular-session day order",
                    swing_exit_order="a GTC OCO order (good-'til-cancelled, one-cancels-the-other)",
                    swing_exit_why="A day stop expires every evening; a GTC one doesn't (most brokers cancel GTC after 60-180 days).",
                    adviser="an SEC-registered investment adviser (check them on adviserinfo.sec.gov)",
                    costs_detail="half-spread, slippage, SEC Section 31 and FINRA TAF sell fees; $0 commission assumed",
                    forward_why=("Momentum is the most replicated price anomaly in US data (Jegadeesh &amp; Titman, 1993), "
                                 "but every backtest of it is flattered by survivorship bias and by years of being known."),
                    forward_rules="docs/us/SWING_RESEARCH_PLAN.md",
                    short_verb="sell short"),
    data_subdir="data-us", docs_subdir="docs/us", default_port=61288,
)
