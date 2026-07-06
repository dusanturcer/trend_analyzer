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
          f"z >= {C.SCREENER_MIN_Z} in the last {W}h...")
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
        df = F.add_baselines(df)
        win = df.iloc[-W:]
        max_z = float(win["vol_z"].max())
        if max_z < C.SCREENER_MIN_Z:
            continue
        price_move = float(df["close"].iloc[-1] / df["close"].iloc[-(W + 1)] - 1)
        silent = abs(price_move) < C.SCREENER_SILENT_MAX_MOVE
        spike_pos = int(win["vol_z"].idxmax())
        hours_ago = len(df) - 1 - spike_pos
        rows.append({
            "coin": c["symbol"], "pair": c["pair"], "rank": c["rank"],
            "max_vol_z": round(max_z, 2),
            "spike_hours_ago": hours_ago,
            f"spike_hours_{W}h": int((win["vol_z"] >= C.SCREENER_MIN_Z).sum()),
            f"price_move_{W}h": f"{price_move:+.1%}",
            "buy_ratio": round(float(win["buy_ratio"].mean()), 3),
            "silent": silent,
        })

    if not rows:
        print(f"\nNo coin currently shows a z>={C.SCREENER_MIN_Z} spike. "
              "Quiet market — re-run later.")
        return
    out = (pd.DataFrame(rows)
           .sort_values(["silent", "max_vol_z"], ascending=[False, False])
           .head(C.SCREENER_TOP_N))
    n_silent = int(out["silent"].sum())
    print(f"\n=== Watchlist: {len(out)} spikes, {n_silent} silent "
          f"(the studied precursor) ===")
    print("(silent=True + high max_vol_z = the profile with ~3-4x "
          "historical lift)\n")
    print(out.to_string(index=False))
    out.to_csv(C.OUT_DIR / "screener_watchlist.csv", index=False)
    print(f"\nSaved to {C.OUT_DIR / 'screener_watchlist.csv'}")
    print("Reminder: even the best segment failed ~84% of the time "
          "historically. Not financial advice.")


if __name__ == "__main__":
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
