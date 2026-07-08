"""Live strategy-B screener: fresh 30d-high breakouts + BTC regime banner.

Reads the cached parquets - refresh first (cheap, incremental):
    cd ..  && python fetch_data.py  && cd breakout
    python screener_b.py

LIVE RULES (backtested): buy the breakout, set a -25% disaster stop,
sell whatever remains after 7 days. No TP - breakout profits live in the
fat right tail (the TP-ladder variant cut EV from +3.7% to +1.5%).
"""
import json

import numpy as np
import pandas as pd

import bconfig as B


def btc_regime():
    p = B.KLINES_DIR / "BTCUSDT.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    c = df["close"]
    if len(c) < 100 * 24:
        return None
    ma = float(c.tail(100 * 24).mean())
    px = float(c.iloc[-1])
    return {"above": px >= ma, "dist": px / ma - 1,
            "asof": df["open_time"].iloc[-1]}


def main():
    B.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(B.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    reg = btc_regime()
    if reg:
        arrow = "ABOVE" if reg["above"] else "BELOW"
        print("=" * 62)
        print(f"BTC REGIME: price {arrow} 100d MA by {reg['dist']:+.1%} "
              f"(as of {reg['asof']:%Y-%m-%d %H:%M} UTC)")
        print("(FYI: strategy B stayed positive even in the below-MA "
              "regime of 2025-H1,\nbut its edge was smaller. Informational "
              "only.)")
        print("=" * 62)

    rows, stale = [], 0
    now = pd.Timestamp.now(tz="UTC")
    files = sorted(B.KLINES_DIR.glob("*.parquet"))
    print(f"\nScanning {len(files)} coins for fresh 30d-high breakouts "
          f"(last {B.FRESH_H}h)...")
    for n, path in enumerate(files, 1):
        if n % 50 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if meta is None:
            continue
        df = pd.read_parquet(path)
        liq = float(df["quote_volume"].tail(24 * 30).median())
        if liq < B.MIN_USD_PER_H or len(df) < B.BREAKOUT_WINDOW_H + 200:
            continue
        age_h = (now - df["open_time"].iloc[-1]).total_seconds() / 3600
        if age_h > 26:
            stale += 1
            continue

        c = df["close"].reset_index(drop=True)
        prior_high = c.shift(1).rolling(B.BREAKOUT_WINDOW_H).max()
        cond = (c > prior_high).fillna(False).to_numpy()
        on = np.flatnonzero(cond & ~np.concatenate(([False], cond[:-1])))
        # dedup and keep only fresh onsets
        fresh = [int(i) for k, i in enumerate(on)
                 if (k == 0 or i - on[k - 1] >= B.MIN_GAP_H)
                 and i >= len(c) - B.FRESH_H]
        if not fresh:
            continue
        i = fresh[-1]
        margin = float(c.iloc[-1] / prior_high.iloc[i] - 1)
        rows.append({
            "coin": meta["symbol"], "pair": path.stem, "rank": meta["rank"],
            "broke_h_ago": len(c) - 1 - i,
            "above_old_high": f"{margin:+.1%}",
            "ret_24h": f"{float(c.iloc[-1] / c.iloc[-25] - 1):+.1%}",
            "vol_z_now": (round(float(df['vol_z'].iloc[-1]), 1)
                          if "vol_z" in df else ""),
            "usd_per_h": f"{liq / 1000:,.0f}k",
        })

    if stale:
        print(f"NOTE: {stale} coins skipped as stale - run the parent "
              "fetch_data.py first.")
    if not rows:
        print("\nNo fresh 30d-high breakouts. Historically ~1 per day "
              "across the universe;\nquiet stretches are normal.")
        return
    out = pd.DataFrame(rows).sort_values("broke_h_ago")
    print(f"\n=== B watchlist: {len(out)} fresh breakouts ===\n")
    print(out.to_string(index=False))
    out.to_csv(B.OUT_DIR / "b_watchlist.csv", index=False)
    print(f"\nSaved to {B.OUT_DIR / 'b_watchlist.csv'}")
    print(f"\nLIVE RULES: buy, set {B.DISASTER_STOP:.0%} stop, sell after "
          "7 days. No TP.\nExpect ~49% winners - the edge is the size of "
          "the wins, not their frequency.\nHistorical: +3.4%/trade with "
          "stop, 6/6 half-years above control - but edge has\nnarrowed "
          "since 2025; monthly re-validation matters. Log every trade. "
          "Not financial advice.")


if __name__ == "__main__":
    main()
