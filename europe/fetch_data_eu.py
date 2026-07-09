"""Build the EUROPE universe: coins with Binance USDT data AND an OKX
USDC spot pair (with real OKX-side turnover), then check candle coverage.

Candles themselves are shared with the parent project - refresh them with
the parent fetcher:

    python fetch_data_eu.py         # build/refresh the EU universe
    python ..\\fetch_data.py         # refresh the shared Binance candles
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))            # europe config shadows parent's
sys.path.insert(1, str(HERE.parent))

import config as C                        # noqa: E402  (europe)
from fetch_data import (top_coins, binance_usdt_symbols,  # noqa: E402
                        get)

assert C.OKX_QUOTE == "USDC", "europe config must be first on sys.path"


def okx_usdc_pairs():
    """base -> instId for live OKX USDC spot pairs."""
    data = get(f"{C.OKX_BASE}/api/v5/public/instruments",
               {"instType": "SPOT"}).get("data", [])
    return {s["baseCcy"].upper(): s["instId"] for s in data
            if s["quoteCcy"] == C.OKX_QUOTE and s["state"] == "live"}


def okx_24h_volumes():
    """instId -> 24h quote turnover (USDC)."""
    data = get(f"{C.OKX_BASE}/api/v5/market/tickers",
               {"instType": "SPOT"}).get("data", [])
    out = {}
    for t in data:
        try:
            out[t["instId"]] = float(t.get("volCcy24h") or 0)
        except (TypeError, ValueError):
            pass
    return out


def main():
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching top coin list from CoinGecko...")
    coins = top_coins()
    print(f"  {len(coins)} coins after exclusions")
    print("Fetching Binance USDT pairs (signal data)...")
    bnc = binance_usdt_symbols()
    print(f"Fetching OKX {C.OKX_QUOTE} spot pairs (execution)...")
    okx = okx_usdc_pairs()
    vols = okx_24h_volumes()

    universe, drop_liq = [], []
    for c in coins:
        if c["symbol"] not in bnc or c["symbol"] not in okx:
            continue
        inst = okx[c["symbol"]]
        v24 = vols.get(inst, 0.0)
        if v24 < C.MIN_OKX_USD_24H:
            drop_liq.append(c["symbol"])
            continue
        universe.append(dict(
            c, pair=bnc[c["symbol"]], exchange="binance",
            okx_pair=inst, okx_usd_24h=round(v24)))

    with open(C.DATA_DIR / "universe.json", "w") as f:
        json.dump(universe, f, indent=1)

    have = sum(1 for c in universe
               if (C.KLINES_DIR / f"{c['pair']}.parquet").exists())
    print(f"\nEU universe: {len(universe)} coins "
          f"(Binance data + OKX {C.OKX_QUOTE} pair with >= "
          f"${C.MIN_OKX_USD_24H:,}/24h)")
    print(f"  dropped for thin OKX books: {len(drop_liq)} "
          f"({', '.join(drop_liq[:12])}{'...' if len(drop_liq) > 12 else ''})")
    print(f"  candles already cached: {have}/{len(universe)}")
    if have < len(universe):
        print("  -> run the parent fetch to complete the cache: "
              "python ..\\fetch_data.py")


if __name__ == "__main__":
    main()
