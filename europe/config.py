"""EUROPE variant: Binance candles for SIGNALS, KRAKEN USD/EUR for EXECUTION.

Venue chosen from exchange_survey.py: Kraken had the widest EU-accessible
listing coverage (241 coins) with real (if modest) books. Key difference
vs the parent system: Kraken Pro base fees ~0.25% maker per side ->
COST_ROUNDTRIP = 0.5%, more than double the Binance assumption. All EU
backtests use this number - strategies must re-earn their stakes at it.

Architecture:
  - Universe: top-500 coins with BOTH a Binance USDT pair (signal data)
    and a Kraken USD/EUR pair with real turnover. Built by fetch_data_eu.py.
  - Candles: SHARED with the parent project (../data/klines) - refresh via
    the parent fetch_data.py; nothing is downloaded twice.
  - All three strategies (E, W, B) available (Binance candles carry taker data).
  - Backtests must be re-run on this RESTRICTED universe at Kraken costs.

This module mirrors the parent config interface so shared engines
(features, detection, analyze, report, validate_edge) work unchanged when
this folder is first on sys.path.
"""
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).parent            # .../trend_analyzer/europe
PARENT = ROOT.parent
DATA_DIR = ROOT / "data"                # europe's own universe.json
KLINES_DIR = PARENT / "data" / "klines" # SHARED Binance candle cache
OUT_DIR = ROOT / "output"
CHARTS_DIR = OUT_DIR / "charts"

# ---------------------------------------------------------------- universe
TOP_N_COINS = 500
QUOTE_ASSET = "USDT"                    # data side (Binance candles)
KRAKEN_QUOTES = ("USD", "EUR")          # execution side (Kraken spot)
EXCLUDE_SYMBOLS = {
    "USDT", "USDC", "DAI", "TUSD", "USDE", "FDUSD", "USDD", "PYUSD",
    "USDS", "USD1", "BUSD", "GUSD", "USDP", "FRAX", "LUSD", "SUSDS",
    "WBTC", "WETH", "WBETH", "WEETH", "STETH", "WSTETH", "RETH", "CBBTC",
    "CBETH", "METH", "RSETH", "EZETH", "SOLVBTC", "LBTC", "JITOSOL",
    "BSC-USD", "XAUT", "PAXG", "EURC", "EURT",
}
MIN_VENUE_USD_24H = 250_000             # min Kraken-side 24h turnover
                                        # ($250k/day ~ $10k/h: workable for
                                        # ~EUR 1k maker orders, no bigger)

# ---------------------------------------------------------------- data window
INTERVAL = "1h"
LOOKBACK_DAYS = 1100
BINANCE_BASE = "https://api.binance.com"
OKX_BASE = "https://www.okx.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
REQUEST_SLEEP = 0.25
KLINE_LIMIT = 1000

# ---------------------------------------------------------------- event detection
PUMP_THRESHOLD = 0.10
PUMP_WINDOW_H = 24
SWEEP_THRESHOLDS = [0.05, 0.10, 0.15, 0.20]
SWEEP_WINDOWS_H = [4, 12, 24]
DETECT_DUMPS = True
MIN_EVENT_GAP_H = 24

# ---------------------------------------------------------------- precursors
PRE_WINDOW_H = 48
BASELINE_DAYS = 30
VOLUME_SPIKE_Z = 2.0
QUIET_VOL_PCTL = 25
N_CONTROL_PER_EVENT = 5
CONTROL_SEED = 42

# ---------------------------------------------------------------- screener
SCREENER_TOP_N = 30
SCREENER_MIN_Z = 3.0
SCREENER_MIN_RANK = 76
SCREENER_WINDOW_H = 24
SCREENER_SILENT_MAX_MOVE = 0.03
SCREENER_MIN_USD_PER_H = 100_000

# ---------------------------------------------------------------- strategies
# (rules copied from validated configs; re-backtest on THIS universe
#  with backtest_strategies.py before live use)
E_MIN_Z = 4.0
E_MIN_RANK = 76
E_SILENT_MAX_MOVE_3H = 0.02
E_TP_LADDER = [(0.08, 0.5), (0.15, 0.5)]
E_TIME_STOP_H = 36

W_SCORE_ALERT = 80
W_HOLD_H = 168
W_DISASTER_STOP = -0.25

B_WINDOW_H = 30 * 24
B_MIN_GAP_H = 48
B_HOLD_H = 168
B_DISASTER_STOP = -0.25

MIN_USD_PER_H = 100_000                 # Binance-side signal liquidity
COST_ROUNDTRIP = 0.005                  # Kraken Pro base: ~0.25% maker/side
