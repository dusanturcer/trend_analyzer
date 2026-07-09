"""Run the full parent analysis (events, precursors, report) on EU data.

    python run_analyze.py       -> europe/output/report.html etc.

Note: buy-ratio / trade-count features are blank (OKX candles lack them);
BTC context uses BTC-USDC if present.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))

import analyze  # noqa: E402  (parent engine, europe config via sys.path)

if __name__ == "__main__":
    analyze.main()
