"""Live W-absorption screener: fresh absorb >= 80 crossings + BTC regime.

Reads the cached parquets, so refresh them first (cheap, incremental):
    cd ..  && python fetch_data.py  && cd whales
    python screener_w.py

Strategy this feeds (backtested variant C): buy the crossing, hold 7 days
flat, sell. No stop, no TP. ~6 positions open on average at full signal flow.

The BTC 100d-MA banner is a REGIME NOTIFICATION, not a tested filter:
in the one historical period when BTC spent most time below trend
(2025-H1), absorption entries underperformed even random ones.
"""
import json

import numpy as np
import pandas as pd

import wconfig as W
from accumulation import add_accumulation

FRESH_CROSS_H = 24          # a crossing counts as "new" for this many hours
BTC_MA_H = 100 * 24         # 100-day MA on hourly closes
TRADE_MIN_USD_PER_H = 100_000


def btc_regime():
    p = W.KLINES_DIR / "BTCUSDT.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    c = df["close"]
    if len(c) < BTC_MA_H:
        return None
    ma = float(c.tail(BTC_MA_H).mean())
    px = float(c.iloc[-1])
    return {"price": px, "ma100d": ma, "above": px >= ma,
            "dist": px / ma - 1, "asof": df["open_time"].iloc[-1]}


def main():
    W.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(W.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    # ---------- BTC regime notification ----------
    reg = btc_regime()
    if reg:
        arrow = "ABOVE" if reg["above"] else "BELOW"
        print("=" * 62)
        print(f"BTC REGIME: price {arrow} 100d MA by {reg['dist']:+.1%} "
              f"(as of {reg['asof']:%Y-%m-%d %H:%M} UTC)")
        if not reg["above"]:
            print("!! CAUTION: in the one such historical period (2025-H1), "
                  "absorption\n!! entries underperformed even random entries. "
                  "Untested as a filter -\n!! treat new W signals with extra "
                  "skepticism while this persists.")
        print("=" * 62)

    rows, stale = [], 0
    now = pd.Timestamp.now(tz="UTC")
    files = sorted(W.KLINES_DIR.glob("*.parquet"))
    print(f"\nScanning {len(files)} coins for fresh absorb >= "
          f"{W.SCORE_ALERT} crossings (last {FRESH_CROSS_H}h)...")
    for n, path in enumerate(files, 1):
        if n % 50 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if meta is None or meta.get("exchange") == "okx":
            continue
        df = pd.read_parquet(path)
        if (df["quote_volume"].tail(24 * 30).median() < TRADE_MIN_USD_PER_H
                or df["trades"].isna().all()):
            continue
        age_h = (now - df["open_time"].iloc[-1]).total_seconds() / 3600
        if age_h > 26:
            stale += 1
            continue
        df = add_accumulation(df)
        hot = (df["absorb"] >= W.SCORE_ALERT).fillna(False).to_numpy()
        cross = hot & ~np.concatenate(([False], hot[:-1]))
        recent = np.flatnonzero(cross[-FRESH_CROSS_H:])
        if not len(recent):
            continue
        i = len(df) - FRESH_CROSS_H + int(recent[-1])
        last = df.iloc[-1]
        rows.append({
            "coin": meta["symbol"], "pair": path.stem, "rank": meta["rank"],
            "crossed_h_ago": len(df) - 1 - i,
            "absorb_now": round(float(last["absorb"]), 1)
                          if np.isfinite(last["absorb"]) else None,
            "clip": round(float(last["clip"]), 0),
            "ret_72h": f"{float(df['close'].iloc[-1] / df['close'].iloc[-W.ACC_WINDOW_H] - 1):+.1%}",
            "usd_per_h": f"{float(df['quote_volume'].tail(720).median())/1000:,.0f}k",
        })

    if stale:
        print(f"NOTE: {stale} coins skipped as stale - run the parent "
              "fetch_data.py first for a complete scan.")
    if not rows:
        print("\nNo fresh absorption crossings. Historically ~1 per day "
              "across the universe, so empty days are normal.")
        return
    out = pd.DataFrame(rows).sort_values("crossed_h_ago")
    print(f"\n=== W watchlist: {len(out)} fresh crossings ===\n")
    print(out.to_string(index=False))
    out.to_csv(W.OUT_DIR / "w_watchlist.csv", index=False)
    print(f"\nSaved to {W.OUT_DIR / 'w_watchlist.csv'}")
    print("\nRules (backtested variant C): buy, hold 7 days flat, sell. "
          "No stop, no TP,\nequal stakes. Log every trade: date, coin, "
          "absorb, entry, exit, PnL, BTC regime.")
    print("Historical: +3.1%/trade raw, +2.9% vs random entries, "
          "5 of 6 half-years positive.\nPaper trade first. "
          "Not financial advice.")


if __name__ == "__main__":
    main()
