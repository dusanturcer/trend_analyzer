"""E-combo strategy configuration.

The one variant that survived (with caveats) the 18-month variant test:
strong silent volume spikes (z >= 4), mid/small/micro/tiny caps, liquid
pairs, NO hard stop-loss, 36h time stop, maker-fee execution (0.2% RT).

Data is shared with the parent trend_analyzer project (../data).
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))          # reuse parent modules

DATA_DIR = PARENT / "data"
KLINES_DIR = DATA_DIR / "klines"
OUT_DIR = HERE / "output"

# ---- strategy (frozen: changing these = a NEW strategy, re-validate!) ----
MIN_Z = 4.0
TIERS = {"mid", "small", "micro", "tiny"}    # rank 76+
MIN_USD_PER_H = 100_000
SILENT_MAX_MOVE_3H = 0.02
TP_LADDER = [(0.08, 0.5), (0.15, 0.5)]
STOP_LOSS = None                              # time stop only
TIME_STOP_H = 36
COST_ROUNDTRIP = 0.002                        # maker fills assumed
ONE_TRADE_PER_COIN = True


def tier_of(rank):
    return ("mega" if rank <= 20 else "large" if rank <= 75
            else "mid" if rank <= 150 else "small" if rank <= 200
            else "micro" if rank <= 350 else "tiny")
