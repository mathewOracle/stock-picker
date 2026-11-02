"""Crypto: the largest liquid coins (stablecoins excluded), priced in US dollars, trading 24/7 on a UTC clock.

Data only, like every profile. Symbols are Yahoo Finance tickers; newer coins carry a CoinMarketCap id in the ticker
(SUI20947-USD), which `short_symbol` hides. Yahoo quotes crypto volume in DOLLARS (not coins), hence volume_in_money.
The coin pages, tokenomics checks and refresh live in app/crypto/; the stock desk, intraday scanner and research
pipeline are not used for this market (24/7 trading has no session open/close to anchor them).
"""

import re
from dataclasses import dataclass
from datetime import date, time
from zoneinfo import ZoneInfo

from app.market.profile import Clock, Market, Money, News, Session, Wording

UTC = ZoneInfo("UTC")

# symbol -> (name, category). Category plays the role a sector plays for stocks: it groups peers in the overview.
COINS: dict[str, tuple[str, str]] = {
    "BTC-USD": ("Bitcoin", "Store of value"),
    "ETH-USD": ("Ethereum", "Smart-contract platform"),
    "XRP-USD": ("XRP", "Payments"),
    "BNB-USD": ("BNB", "Exchange token"),
    "SOL-USD": ("Solana", "Smart-contract platform"),
    "TRX-USD": ("TRON", "Smart-contract platform"),
    "DOGE-USD": ("Dogecoin", "Meme"),
    "ADA-USD": ("Cardano", "Smart-contract platform"),
    "LINK-USD": ("Chainlink", "Infrastructure"),
    "XLM-USD": ("Stellar", "Payments"),
    "BCH-USD": ("Bitcoin Cash", "Payments"),
    "AVAX-USD": ("Avalanche", "Smart-contract platform"),
    "SUI20947-USD": ("Sui", "Smart-contract platform"),
    "LTC-USD": ("Litecoin", "Payments"),
    "HBAR-USD": ("Hedera", "Smart-contract platform"),
    "SHIB-USD": ("Shiba Inu", "Meme"),
    "DOT-USD": ("Polkadot", "Interoperability"),
    "UNI7083-USD": ("Uniswap", "DeFi"),
    "XMR-USD": ("Monero", "Privacy"),
    "NEAR-USD": ("NEAR Protocol", "Smart-contract platform"),
    "AAVE-USD": ("Aave", "DeFi"),
    "APT21794-USD": ("Aptos", "Smart-contract platform"),
    "ICP-USD": ("Internet Computer", "Smart-contract platform"),
    "ETC-USD": ("Ethereum Classic", "Smart-contract platform"),
    "PEPE24478-USD": ("Pepe", "Meme"),
    "ATOM-USD": ("Cosmos", "Interoperability"),
    "FIL-USD": ("Filecoin", "Infrastructure"),
    "ARB11841-USD": ("Arbitrum", "Layer 2"),
    "OP-USD": ("Optimism", "Layer 2"),
    "POL28321-USD": ("Polygon", "Layer 2"),
    "ALGO-USD": ("Algorand", "Smart-contract platform"),
    "RENDER-USD": ("Render", "Infrastructure"),
    "INJ-USD": ("Injective", "DeFi"),
}
MEME = "Meme"

# Macro context only (risk appetite, the dollar, the other "hard asset"). Weekday series: 252 bars a year, not 365.
INDICES: dict[str, str] = {
    "^GSPC": "S&P 500", "^IXIC": "Nasdaq Composite", "DX-Y.NYB": "US Dollar Index", "GC=F": "Gold",
}


@dataclass(frozen=True)
class CryptoMarket(Market):
    categories: tuple[tuple[str, str], ...] = ()   # (symbol, category) pairs; a tuple keeps the profile frozen

    def session(self, day: date) -> Session | None:
        return Session(time(0, 0), time(23, 59))   # every day, all day: no weekends, no holidays

    @property
    def knows_holidays(self) -> bool:
        return True   # there are none to know

    def short_symbol(self, symbol: str) -> str:
        """BTC-USD -> BTC, SUI20947-USD -> SUI (Yahoo appends a CoinMarketCap id to newer tickers)."""
        return re.sub(r"\d+$", "", symbol.removesuffix("-USD"))

    def category(self, symbol: str) -> str:
        return dict(self.categories).get(symbol, "Other")


MARKET = CryptoMarket(
    key="crypto", app_name="Stock Picker", short_name="Crypto", exchange="Crypto 24/7", regulator="your country's regulator",
    clock=Clock(tz=UTC, open=time(0, 0), close=time(23, 59), early_label="Open 24/7", early_start=time(0, 0),
                overnight_label="Open 24/7"),
    stocks={symbol: name for symbol, (name, _) in COINS.items()},
    categories=tuple((symbol, category) for symbol, (_, category) in COINS.items()),
    indices=INDICES, benchmark="BTC-USD", benchmark_name="Bitcoin", vix="", vix_name="Bitcoin 30-day volatility",
    money=Money("$", 1e6, "M", steps=((1e12, "T"), (1e9, "B"), (1e6, "M"))),
    # spot exchanges charge ~0.1% taker; spread + slippage on large coins adds ~0.05-0.1%. 0.2% a side is deliberately high.
    swing_cost_per_side=0.002,
    intraday_cost_per_side=0.002,
    min_traded_value=50,            # $M/day: below this a coin's market is too thin to trust its chart
    news=News(locale="hl=en-US&gl=US&ceid=US:en", finance_terms="(crypto OR cryptocurrency OR token OR blockchain)"),
    u2_candidates=(),
    broker_name="broker-neutral",
    wording=Wording(intraday_product="a spot order (no leverage)",
                    swing_product="a spot buy (no leverage, no perpetual futures)",
                    swing_exit_order="an OCO order (one-cancels-the-other) resting on the exchange",
                    swing_exit_why="Crypto never closes: the stop has to be resting on the exchange while you sleep.",
                    adviser="a registered investment adviser who covers crypto-assets",
                    costs_detail="exchange taker fee, spread and slippage",
                    forward_why="Crypto signals have not been forward-tested in this app yet.",
                    forward_rules="not pre-registered yet",
                    short_verb="sell short"),
    data_subdir="data-crypto", docs_subdir="docs/crypto", default_port=61289,
    trading_days=365, volume_in_money=True, worker="app.crypto.main:app",
)
