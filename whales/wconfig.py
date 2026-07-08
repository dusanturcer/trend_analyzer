"""Whale scanner configuration.

What "whale accumulation" looks like in public exchange data:
  1. Sustained buy pressure  - taker-buy share elevated for days, not hours
  2. Bigger average clips    - quote volume per trade creeps up
  3. Quiet price             - batches are sized to NOT move the market
  4. Flow/price divergence   - money flows in, price goes nowhere (yet)
  5. (live) repeated equal-size prints = TWAP/iceberg execution bots

Data: shared with parent project (../data). Binance coins only - OKX
candles lack taker-buy and trade-count fields.
"""
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))

DATA_DIR = PARENT / "data"
KLINES_DIR = DATA_DIR / "klines"
OUT_DIR = HERE / "output"

# ---- accumulation score (hourly klines) ----
ACC_WINDOW_H = 72          # accumulation window: 3 days of batches
RANK_WINDOW_H = 24 * 90    # percentile ranks vs coin's own last 90 days
QUIET_MAX_ABS_RET = 0.08   # price must have moved < this over the window
MIN_USD_PER_H = 50_000     # liquidity floor (lower than E-combo: watching, not trading)
SCORE_ALERT = 80           # composite score (0-100) worth attention

# ---- live large-trade scanner (aggTrades) ----
BIG_TRADE_USD = 25_000     # a single print this size = whale-ish for mid caps
SCAN_HOURS = 6             # how far back the live scanner looks
TWAP_MIN_REPEATS = 5       # >= N near-identical clip sizes = execution algo
TWAP_SIZE_TOL = 0.02       # sizes within 2% count as "identical"

# ---- validation ----
FWD_HORIZON_H = 168        # does accumulation predict the NEXT 7 days?
FWD_GOOD_RET = 0.10        # "payoff" = >= +10% within horizon

# ---- W strategy (live rules) ----
# Disaster stop: NOT an edge decision, a tail-insurance decision.
# Sweep (stop_sweep.py): costs ~0.26%/trade, fires on ~5% of trades,
# caps worst observed -37.8% at -25.2%, win rate unchanged (48%).
DISASTER_STOP = -0.25
