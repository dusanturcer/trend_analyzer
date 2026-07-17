"""Strategy F pilot - wick catcher (resting bids), CALIBRATION MODE.

Purpose of this pilot is to MEASURE, not to earn: backtests cannot verify
whether resting bids actually fill at wick extremes (phantom-fill bias),
and neither can paper trading. Only tiny real orders can.

Frozen pilot rules (EU backtest C_12pct: +5.74%/trade, 92% win, 6/6
half-years at 0.5% costs - treat as an optimistic upper bound due to
phantom-fill and survivorship bias):

  - Universe: the N most liquid Kraken-tradeable coins (from ../europe)
  - Bid: 12% below the latest close, re-priced once per day
  - TP limit: +8% over entry, placed immediately after any fill
  - Time stop: close at 48h if neither TP nor stop hit
  - Disaster stop: -25% below entry
  - Stake: EUR 100-200 per bid. Calibration money, not earning money.
  - Max concurrent open POSITIONS: 3 (cascade days fill many bids at once)

Pilot protocol: run 3 months, log every fill in fill_log.csv, then compare
realized fill rate and EV against backtest prediction (see README).
"""
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))

KLINES_DIR = PARENT / "data" / "klines"
EU_UNIVERSE = PARENT / "europe" / "data" / "universe.json"
OUT_DIR = HERE / "output"

N_COINS = 10            # most liquid Kraken names only
DEPTH = 0.12            # bid 12% below last close
TP = 0.08               # take-profit over entry
TIME_STOP_H = 48
DISASTER_STOP = -0.25
STAKE_EUR = (100, 200)  # calibration size
MAX_OPEN_POSITIONS = 3
