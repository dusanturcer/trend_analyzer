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
    """instId -> 24h quote turnover (USDC), robust to field ambiguity."""
    data = get(f"{C.OKX_BASE}/api/v5/market/tickers",
               {"instType": "SPOT"}).get("data", [])
    out = {}
    for t in data:
        try:
            last = float(t.get("last") or 0)
            vol_base = float(t.get("vol24h") or 0)       # base units
            vol_quote = float(t.get("volCcy24h") or 0)   # quote units (spot)
            # sanity: quote turnover should ~= base volume x price;
            # take whichever interpretation is consistent
            candidates = [vol_quote, vol_base * last]
            out[t["instId"]] = max(c for c in candidates if c >= 0)
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

    on_bnc = [c for c in coins if c["symbol"] in bnc]
    on_both = [c for c in on_bnc if c["symbol"] in okx]
    print(f"\nDIAGNOSTICS: top-{len(coins)} coins -> {len(on_bnc)} on "
          f"Binance -> {len(on_both)} also have an OKX {C.OKX_QUOTE} pair")
    v_all = sorted((vols.get(okx[c["symbol"]], 0.0) for c in on_both),
                   reverse=True)
    if v_all:
        print("OKX 24h turnover distribution of those: "
              f"max ${v_all[0]:,.0f} | median ${v_all[len(v_all)//2]:,.0f} "
              f"| >=$1M: {sum(1 for v in v_all if v >= 1e6)} "
              f"| >=$250k: {sum(1 for v in v_all if v >= 250e3)} "
              f"| >=$50k: {sum(1 for v in v_all if v >= 50e3)}")

    universe, drop_liq = [], []
    for c in on_both:
        inst = okx[c["symbol"]]
        v24 = vols.get(inst, 0.0)
        if v24 < C.MIN_OKX_USD_24H:
            drop_liq.append(f"{c['symbol']}(${v24/1e3:,.0f}k)")
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
