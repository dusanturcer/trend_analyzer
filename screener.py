"""Live screener: which coins show the precursor signature RIGHT NOW?

Signature = recent volume spike (hour-of-day-adjusted z >= VOLUME_SPIKE_Z)
while price hasn't moved much yet ("silent spike").

    python screener.py
"""
import json
import time

import numpy as np
import pandas as pd

import config as C
import features as F
from fetch_data import fetch_klines, get


def main():
    with open(C.DATA_DIR / "universe.json") as f:
        universe = json.load(f)

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (C.BASELINE_DAYS + 3) * 24 * 3600 * 1000

    rows = []
    print(f"Scanning {len(universe)} coins for silent volume spikes...")
    for i, c in enumerate(universe, 1):
        if i % 25 == 0:
            print(f"  {i}/{len(universe)}")
        try:
            df = fetch_klines(c["pair"], start_ms, now_ms)
        except Exception as e:
            print(f"  {c['pair']}: {e}")
            continue
        if df is None or len(df) < 24 * 10:
            continue
        df = F.add_baselines(df)
        last12 = df.iloc[-12:]
        max_z = float(last12["vol_z"].max())
        if max_z < C.VOLUME_SPIKE_Z:
            continue
        price_move = float(df["close"].iloc[-1] / df["close"].iloc[-13] - 1)
        rows.append({
            "coin": c["symbol"], "pair": c["pair"], "rank": c["rank"],
            "max_vol_z_12h": round(max_z, 2),
            "spike_hours_12h": int((last12["vol_z"] >= C.VOLUME_SPIKE_Z).sum()),
            "price_move_12h": f"{price_move:+.1%}",
            "buy_ratio_12h": round(float(last12["buy_ratio"].mean()), 3),
            "silent": abs(price_move) < 0.03,
        })

    if not rows:
        print("No coins currently show a volume spike. Quiet market.")
        return
    out = (pd.DataFrame(rows)
           .sort_values(["silent", "max_vol_z_12h"], ascending=[False, False])
           .head(C.SCREENER_TOP_N))
    print("\n=== Watchlist: volume spikes in the last 12h ===")
    print("(silent=True means price hasn't moved yet — the studied precursor)\n")
    print(out.to_string(index=False))
    out.to_csv(C.OUT_DIR / "screener_watchlist.csv", index=False)
    print(f"\nSaved to {C.OUT_DIR / 'screener_watchlist.csv'}")
    print("Historical hit rates for this signal are in output/report.html §2.")


if __name__ == "__main__":
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
