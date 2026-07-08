"""Strategy B (30d-high breakout) configuration.

Validated 3y backtest (experiments/backtest_breakout.py, 1123 trades):
EV +3.65%/trade (no stop) / +3.35% (with -25% stop), PF 1.78, beat the
random-entry control in 6 of 6 half-years - including 2025-H1, the regime
that hurt strategies E and W. Caveat: excess has shrunk from ~+3% (2023-24)
to ~+0.9% (2025-26); re-validate monthly.

Frozen live rules: changing these = a NEW strategy, re-validate first.
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

# ---- live rules (backtest variant B_disaster) ----
BREAKOUT_WINDOW_H = 30 * 24     # prior high lookback: 30 days
MIN_GAP_H = 48                  # dedup: one signal per coin per 48h
MIN_USD_PER_H = 100_000         # liquidity floor
HOLD_H = 168                    # hold 7 days
DISASTER_STOP = -0.25           # tail insurance (costs ~0.30%/trade)
COST_ASSUMED = 0.002            # maker execution assumed
FRESH_H = 24                    # screener: breakouts newer than this
