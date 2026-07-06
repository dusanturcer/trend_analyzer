"""Central configuration for the crypto pump analyzer."""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
KLINES_DIR = DATA_DIR / "klines"        # one parquet per symbol
OUT_DIR = ROOT / "output"
CHARTS_DIR = OUT_DIR / "charts"

# ---------------------------------------------------------------- universe
TOP_N_COINS = 200                        # by market cap (CoinGecko)
QUOTE_ASSET = "USDT"
# stablecoins / wrapped assets to exclude from the universe
EXCLUDE_SYMBOLS = {
    "USDT", "USDC", "DAI", "TUSD", "USDE", "FDUSD", "USDD", "PYUSD",
    "USDS", "USD1", "BUSD", "GUSD", "USDP", "FRAX", "LUSD", "SUSDS",
    "WBTC", "WETH", "WBETH", "WEETH", "STETH", "WSTETH", "RETH", "CBBTC",
    "CBETH", "METH", "RSETH", "EZETH", "SOLVBTC", "LBTC", "JITOSOL",
    "BSC-USD", "XAUT", "PAXG",
}

# ---------------------------------------------------------------- data window
INTERVAL = "1h"
LOOKBACK_DAYS = 183                      # ~6 months
BINANCE_BASE = "https://api.binance.com"
OKX_BASE = "https://www.okx.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
REQUEST_SLEEP = 0.25                     # seconds between Binance requests
KLINE_LIMIT = 1000                       # max candles per request

# ---------------------------------------------------------------- event detection
# Primary definition of a "quick jump"
PUMP_THRESHOLD = 0.10                    # +10 %
PUMP_WINDOW_H = 24                       # within 24 hours
# sweep grid: every (threshold, window) combination is also reported
SWEEP_THRESHOLDS = [0.05, 0.10, 0.15, 0.20]
SWEEP_WINDOWS_H = [4, 12, 24]
DETECT_DUMPS = True                      # mirror detection for quick drops
MIN_EVENT_GAP_H = 24                     # merge/dedupe events closer than this

# ---------------------------------------------------------------- precursor analysis
PRE_WINDOW_H = 48                        # hours before event start to inspect
BASELINE_DAYS = 30                       # trailing baseline for volume z-score
VOLUME_SPIKE_Z = 2.0                     # z-score that counts as "volume spike"
QUIET_VOL_PCTL = 25                      # "coiling" = pre-event volatility below this percentile
N_CONTROL_PER_EVENT = 5                  # random non-event windows per event (control group)
CONTROL_SEED = 42

# ---------------------------------------------------------------- screener
SCREENER_TOP_N = 30                      # how many candidates to print
# tuned to the segment where 6-month history showed real lift:
SCREENER_MIN_Z = 3.0                     # only strong spikes (hist: z>4 ~3.9x lift)
SCREENER_MIN_RANK = 76                   # mid+small caps only (rank 76-200)
SCREENER_WINDOW_H = 24                   # scan window (median lead time was ~32h)
SCREENER_SILENT_MAX_MOVE = 0.03          # "price still flat" = |move| < 3%
