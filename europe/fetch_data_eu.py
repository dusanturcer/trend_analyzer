"""Build the EUROPE universe: coins with Binance USDT data AND a Kraken
USD/EUR pair with real turnover, then check candle coverage.

Candles are shared with the parent project - refresh with the parent
fetcher:

    python fetch_data_eu.py         # build/refresh the EU universe
    python ..\\fetch_data.py         # refresh the shared Binance candles
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))            # europe config shadows parent's
sys.path.insert(1, str(HERE.parent))

import config as C                        # noqa: E402  (europe)
from fetch_data import (top_coins, binance_usdt_symbols,  # noqa: E402
                        get)

assert hasattr(C, "KRAKEN_QUOTES"), "europe config must be first on sys.path"

KRAKEN_ALIAS = {"XBT": "BTC", "XDG": "DOGE"}


def kraken_pairs_and_volumes():
    """base symbol -> (wsname, 24h quote turnover USD-ish)."""
    ap = get("https://api.kraken.com/0/public/AssetPairs").get("result", {})
    kmap = {}
    for key, v in ap.items():
        ws = v.get("wsname", "")
        if "/" not in ws:
            continue
        base, quote = ws.split("/")
        base = KRAKEN_ALIAS.get(base, base).upper()
        if quote in C.KRAKEN_QUOTES:
            if base not in kmap or quote == "USD":     # prefer USD book
                kmap[base] = (key, ws)
    out = {}
    keys = [k for k, _ in kmap.values()]
    for i in range(0, len(keys), 100):
        chunk = ",".join(keys[i:i + 100])
        res = get("https://api.kraken.com/0/public/Ticker",
                  {"pair": chunk}).get("result", {})
        for base, (key, ws) in kmap.items():
            t = res.get(key)
            if t:
                try:
                    out[base] = (ws, float(t["v"][1]) * float(t["p"][1]))
                except (TypeError, ValueError, KeyError):
                    pass
        time.sleep(1)
    return out


def main():
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching top coin list from CoinGecko...")
    coins = top_coins()
    print(f"  {len(coins)} coins after exclusions")
    print("Fetching Binance USDT pairs (signal data)...")
    bnc = binance_usdt_symbols()
    print("Fetching Kraken USD/EUR pairs + 24h volumes (execution)...")
    krk = kraken_pairs_and_volumes()

    on_bnc = [c for c in coins if c["symbol"] in bnc]
    on_both = [c for c in on_bnc if c["symbol"] in krk]
    v_all = sorted((krk[c["symbol"]][1] for c in on_both), reverse=True)
    print(f"\nDIAGNOSTICS: top-{len(coins)} -> {len(on_bnc)} on Binance "
          f"-> {len(on_both)} also on Kraken (USD/EUR)")
    if v_all:
        print("Kraken 24h turnover of those: "
              f"max ${v_all[0]:,.0f} | median ${v_all[len(v_all)//2]:,.0f} "
              f"| >=$1M: {sum(1 for v in v_all if v >= 1e6)} "
              f"| >=$250k: {sum(1 for v in v_all if v >= 250e3)} "
              f"| >=$50k: {sum(1 for v in v_all if v >= 50e3)}")

    universe, drop_liq = [], []
    for c in on_both:
        ws, v24 = krk[c["symbol"]]
        if v24 < C.MIN_VENUE_USD_24H:
            drop_liq.append(f"{c['symbol']}(${v24/1e3:,.0f}k)")
            continue
        universe.append(dict(
            c, pair=bnc[c["symbol"]], exchange="binance",
            exec_pair=ws, venue="kraken", venue_usd_24h=round(v24)))

    with open(C.DATA_DIR / "universe.json", "w") as f:
        json.dump(universe, f, indent=1)

    have = sum(1 for c in universe
               if (C.KLINES_DIR / f"{c['pair']}.parquet").exists())
    print(f"\nEU universe: {len(universe)} coins (Binance data + Kraken "
          f"pair with >= ${C.MIN_VENUE_USD_24H:,}/24h)")
    print(f"  dropped for thin Kraken books: {len(drop_liq)} "
          f"({', '.join(drop_liq[:12])}{'...' if len(drop_liq) > 12 else ''})")
    print(f"  candles already cached: {have}/{len(universe)}")
    if have < len(universe):
        print("  -> run the parent fetch to complete the cache: "
              "python ..\\fetch_data.py")


if __name__ == "__main__":
    main()
