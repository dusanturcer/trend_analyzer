"""Live E-combo screener: strong silent spikes happening NOW, with the
extra indicators shown so you can apply any insight from correlate.py.

    python screener_e.py
"""
import json
import time

import pandas as pd

import econfig as E
import features as F                      # parent modules
from fetch_data import fetch_klines, fetch_okx_klines
from indicators import add_indicators


def main():
    E.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(E.DATA_DIR / "universe.json") as f:
        universe = json.load(f)
    targets = [c for c in universe if E.tier_of(c["rank"]) in E.TIERS]

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 40 * 24 * 3600 * 1000

    rows = []
    print(f"Scanning {len(targets)} coins for E-combo signals "
          f"(z>={E.MIN_Z}, silent, liquid)...")
    for i, c in enumerate(targets, 1):
        if i % 25 == 0:
            print(f"  {i}/{len(targets)}")
        try:
            fetch = (fetch_okx_klines if c.get("exchange") == "okx"
                     else fetch_klines)
            df = fetch(c["pair"], start_ms, now_ms)
        except Exception as e:
            print(f"  {c['pair']}: {e}")
            continue
        if df is None or len(df) < 24 * 10:
            continue
        liq = float(df["quote_volume"].tail(24 * 30).median())
        if liq < E.MIN_USD_PER_H:
            continue
        df = add_indicators(F.add_baselines(df))
        win = df.iloc[-24:]
        max_z = float(win["vol_z"].max())
        if max_z < 2.0:            # show weaker spikes too (watch-only)
            continue
        move3h = float(df["close"].iloc[-1] / df["close"].iloc[-4] - 1)
        last = df.iloc[-1]
        spike_ago = len(df) - 1 - int(win["vol_z"].idxmax())
        grade = ("z4 TRADE" if max_z >= 4 else
                 "z3 watch" if max_z >= 3 else "z2 watch")
        rows.append({
            "grade": grade,
            "coin": c["symbol"], "pair": c["pair"], "rank": c["rank"],
            "max_z_24h": round(max_z, 2),
            "spike_h_ago": spike_ago,
            "move_3h": f"{move3h:+.1%}",
            "silent": abs(move3h) < E.SILENT_MAX_MOVE_3H,
            "usd_per_h": f"{liq/1000:,.0f}k",
            "rsi14": round(float(last["rsi14"]), 0),
            "dist_30d_high": f"{float(last['dist_30d_high']):+.0%}",
            "obv_chg_pctl": round(float(last["obv_chg_pctl"]), 0),
            "bbw_pctl": round(float(last["bbw_pctl"]), 0),
        })

    if not rows:
        print("\nNo volume spikes (z>=2) anywhere right now. Quiet market.")
        return
    out = pd.DataFrame(rows).sort_values(
        ["max_z_24h"], ascending=False)
    tradeable = out[(out["grade"] == "z4 TRADE") & out["silent"]]
    print(f"\n=== E-combo screen: {len(tradeable)} tradeable (z>=4 & silent), "
          f"{len(out)} spikes total ===\n")
    print(out.to_string(index=False))
    out.to_csv(E.OUT_DIR / "e_watchlist.csv", index=False)
    print(f"\nSaved to {E.OUT_DIR / 'e_watchlist.csv'}")
    print("\nONLY 'z4 TRADE' + silent=True rows meet the validated strategy "
          "(3y: 64% win, +1.6%/trade).")
    print("z2/z3 rows are for observation only - historical hit rates were "
          "~9% (z2-3) and ~12% (z3-4) vs 18% (z4+), and the z3 backtest "
          "variant was NOT profitable after costs.")


if __name__ == "__main__":
    main()
