# Crypto analysis

The Crypto tab ranks the 33 largest liquid coins (stablecoins excluded) with the same three-pillar method as the
stock pages, adapted where coins differ from companies. Code: `app/crypto/`, profile: `app/market/crypto.py`.

**Not investment advice, and not backtested.** The stock rules earned their place through a backtest and a forward
test; the crypto rules have neither yet, so every crypto Buy is a research shortlist, not a validated signal.

## What changes for a 24/7 market

| | Stocks | Crypto |
|---|---|---|
| Bars per year / month / quarter | 252 / 21 / 63 | 365 / 30 / 91 (`Market.trading_days`, `Market.spans`) |
| Volume from Yahoo | shares (traded value = close x volume) | already dollars (`Market.volume_in_money`) |
| Price precision | 2 decimals | 6 significant figures, at least 2 decimals (`app/prices.py`): XRP $1.25381, SHIB $0.00000462 |
| Benchmark / relative strength | Nifty 50 / S&P 500 | Bitcoin |
| Fear gauge | VIX | Bitcoin's 30-day realised volatility |
| Exit order | broker-specific | OCO resting on the exchange: the market never closes, so the stop must already be live |

## Pillars and weights

Composite = 30% tokenomics + 40% technical + 30% chart (stocks: 40/35/25). Coins move on momentum and flows far
more than on "value", so technicals weigh more. Technical and chart analysis use the stock code unchanged.

### Tokenomics (`app/crypto/tokenomics.py`)

Each check scores -1..+1 with a weight; the pillar maps to 0-100 (50 = neutral). Missing data is skipped, never guessed.

| Check | Weight | Best | Worst |
|---|---|---|---|
| Network size (market cap) | 1.5 | >= $100B | < $1B |
| Liquidity (3-month avg dollar volume / market cap) | 1.5 | 1-15% a day | < 0.5% (illiquid) or > 30% (frenzy / wash trading) |
| Dilution overhang (FDV / market cap) | 2.0 | <= 1.1x | > 3x (most supply still locked) |
| Supply cap | 1.0 | fixed maximum | open-ended issuance |
| Supply inflation, measured | 1.5 | shrinking or < 1%/yr | > 15%/yr |
| Track record (years since launch) | 1.0 | >= 8 years | < 2 years |
| Distance from all-time high | 1.0 | within 25% | down > 85% |
| Utility claim | 1.0 | (not a meme coin) | meme coin |

Supply inflation is *measured*: every refresh stores each coin's circulating supply, and the check scores once 30+
days of snapshots exist (until then it is shown as "collecting" with weight 0).

## Verdict gates

Same thresholds as stocks (composite, each pillar, reward/risk). Hard flags that veto any buy:

* **Falling knife**: shared with stocks: below the 200-day average, more than 30% off the 52-week high, Supertrend down.
* **Heavy dilution**: FDV more than 3x the market cap.
* **Illiquid**: trades under 0.5% of its market cap a day.
* **Coarse price data**: under half of the last year's closes are distinct. Yahoo rounds daily bars to 6 decimals,
  which leaves SHIB and PEPE with one or two significant figures. ATR, levels and targets computed on that staircase
  are meaningless, so these coins can never be rated a Buy until a more precise source is added.

Soft flags (shown, not vetoes): meme coin, young coin (< 2 years), down > 85% from the all-time high.

## Market context (overview page)

* **Regime** from Bitcoin: below its 200-day average and > 20% off its high = crypto winter; below the 200-day = weak;
  above it with 30-day volatility > 70% = violent uptrend; otherwise healthy.
* **Altcoin season index**: share of altcoins beating Bitcoin over 3 months (>= 75% altcoin season, <= 25% Bitcoin season).
* **Bitcoin dominance** and **breadth** across the tracked coins only (not the whole market).
* **Macro backdrop**: S&P 500, Nasdaq, US Dollar Index, gold (weekday series keep a 252-bar year).

## Not covered

No free, reliable source here for on-chain activity (active addresses, fees, exchange flows), developer activity,
token-unlock calendars, staking yields, exchange solvency or regulatory news. These are not scored, and the coin page
says so rather than treating them as neutral.

## Data

Yahoo Finance (sourced from CoinMarketCap) through the shared refresh in `app/data.py`: two years of daily bars plus
supply and valuation fields, fundamentals re-fetched daily. Like the other markets there is no proxy in the code;
export `HTTPS_PROXY` if your network needs one.
