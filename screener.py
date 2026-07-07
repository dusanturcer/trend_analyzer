"""Live screener, tuned to the profile that showed real lift in the 6-month
backtest: strong silent volume spikes (z >= SCREENER_MIN_Z) on mid/small caps
(rank >= SCREENER_MIN_RANK), scanning the last SCREENER_WINDOW_H hours.

Historical hit rates (see output/report.html §2): silent spike z>4 on
small caps ~16% chance of a >=10% pump within 24h vs 4% base rate (~4x lift).
Still fails most of the time — treat as a watchlist, not a buy signal.

    python screener.py
"""
import json
import time

import numpy as np
import pandas as pd

import config as C
import features as F
from fetch_data import fetch_klines, fetch_okx_klines


def main():
    with open(C.DATA_DIR / "universe.json") as f:
        universe = json.load(f)
    targets = [c for c in universe if c["rank"] >= C.SCREENER_MIN_RANK]

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (C.BASELINE_DAYS + 5) * 24 * 3600 * 1000
    W = C.SCREENER_WINDOW_H

    rows = []
    print(f"Scanning {len(targets)} mid/small-cap coins "
          f"(rank >= {C.SCREENER_MIN_RANK}) for silent spikes "
          f"z >= {C.SCREENER_MIN_Z} in the last {W}h "
          f"(liquidity >= ${C.SCREENER_MIN_USD_PER_H:,.0f}/h)...")
    for i, c in enumerate(targets, 1):
        if i % 25 == 0:
            print(f"  {i}/{len(targets)}")
        try:
            if c.get("exchange") == "okx":
                df = fetch_okx_klines(c["pair"], start_ms, now_ms)
            else:
                df = fetch_klines(c["pair"], start_ms, now_ms)
        except Exception as e:
            print(f"  {c['pair']}: {e}")
            continue
        if df is None or len(df) < 24 * 10:
            continue
        # liquidity filter: median hourly dollar volume over the last 30 days
        liq = float(df["quote_volume"].tail(24 * 30).median())
        if liq < C.SCREENER_MIN_USD_PER_H:
            continue
        df = F.add_baselines(df)
        win = df.iloc[-W:]
        max_z = float(win["vol_z"].max())
        if max_z < 2.0:              # weaker spikes shown as watch-only
            continue
        price_move = float(df["close"].iloc[-1] / df["close"].iloc[-(W + 1)] - 1)
        silent = abs(price_move) < C.SCREENER_SILENT_MAX_MOVE
        spike_pos = int(win["vol_z"].idxmax())
        hours_ago = len(df) - 1 - spike_pos
        grade = ("z4 TRADE" if max_z >= 4 else
                 "z3 watch" if max_z >= 3 else "z2 watch")
        rows.append({
            "grade": grade,
            "coin": c["symbol"], "pair": c["pair"], "rank": c["rank"],
            "max_vol_z": round(max_z, 2),
            "spike_hours_ago": hours_ago,
            f"spike_hours_{W}h": int((win["vol_z"] >= C.SCREENER_MIN_Z).sum()),
            f"price_move_{W}h": f"{price_move:+.1%}",
            "buy_ratio": round(float(win["buy_ratio"].mean()), 3),
            "usd_per_h": f"{liq / 1000:,.0f}k",
            "silent": silent,
        })

    if not rows:
        print("\nNo coin currently shows a z>=2 spike. Quiet market.")
        return
    out = (pd.DataFrame(rows)
           .sort_values("max_vol_z", ascending=False)
           .head(C.SCREENER_TOP_N))
    n_trade = int(((out["grade"] == "z4 TRADE") & out["silent"]).sum())
    print(f"\n=== Watchlist: {len(out)} spikes, "
          f"{n_trade} tradeable (z>=4 & silent) ===")
    print("(z2/z3 = watch-only: historical hit ~9-12% vs ~18% for z4+, "
          "and z3 was not profitable after costs)\n")
    print(out.to_string(index=False))
    out.to_csv(C.OUT_DIR / "screener_watchlist.csv", index=False)
    print(f"\nSaved to {C.OUT_DIR / 'screener_watchlist.csv'}")
    print("Reminder: even the best segment failed ~84% of the time "
          "historically. Not financial advice.")


if __name__ == "__main__":
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
