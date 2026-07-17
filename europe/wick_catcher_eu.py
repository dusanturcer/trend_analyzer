"""Wick-catcher backtest on the EU (Kraken-tradeable) universe at Kraken
costs (0.5% round-trip). See ../experiments/wick_catcher.py for rules.

Expectations set in advance: far fewer fills (~46 coins, and majors wick
less than small caps), EV compressed by the higher costs. The survivorship
and venue-local-wick caveats apply DOUBLY here - Binance lows are used as
fill proxies for bids that would rest on Kraken.

    python wick_catcher_eu.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(1, str(HERE.parent))

from wick_catcher import main  # noqa: E402

if __name__ == "__main__":
    main(cost=0.005,
         universe_path=HERE / "data" / "universe.json",
         tag="eu_kraken")
