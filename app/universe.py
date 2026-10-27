"""The active market's investable universe (profiles live in app/market/).

Kept as a module so every engine import stays `from app.universe import STOCKS`: the engine never knows
which market it is running.
"""

from app.market import MARKET

STOCKS: dict[str, str] = MARKET.stocks
INDICES: dict[str, str] = MARKET.indices
BENCHMARK: str = MARKET.benchmark
VIX: str = MARKET.vix
