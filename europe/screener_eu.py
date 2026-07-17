"""Europe daily screener: E + W + B signals on Binance candles, restricted
to coins tradeable on Kraken (USD/EUR). Each row shows the Kraken pair to
execute on and its Kraken-side 24h turnover.

    python fetch_data_eu.py      # refresh EU universe (weekly is fine)
    python ..\\fetch_data.py      # refresh shared candles (daily)
    python screener_eu.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
sys.path.insert(2, str(HERE.parent / "whales"))

import config as C          # noqa: E402  (europe)
import features as F        # noqa: E402
from accumulation import add_accumulation  # noqa: E402

FRESH_H = 24


def btc_regime():
    p = C.KLINES_DIR / "BTCUSDT.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    c = df["close"]
    if len(c) < 100 * 24:
        return None
    ma = float(c.tail(100 * 24).mean())
    return {"above": float(c.iloc[-1]) >= ma,
            "dist": float(c.iloc[-1]) / ma - 1,
            "asof": df["open_time"].iloc[-1]}


def main():
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    reg = btc_regime()
    if reg:
        arrow = "ABOVE" if reg["above"] else "BELOW"
        print("=" * 62)
        print(f"BTC REGIME: price {arrow} 100d MA by {reg['dist']:+.1%} "
              f"(as of {reg['asof']:%Y-%m-%d %H:%M} UTC)")
        if not reg["above"]:
            print("!! CAUTION: W historically underperformed random in "
                  "below-MA regimes.")
        print("=" * 62)

    e_rows, w_rows, b_rows, stale = [], [], [], 0
    now = pd.Timestamp.now(tz="UTC")
    files = [p for p in sorted(C.KLINES_DIR.glob("*.parquet"))
             if p.stem in universe]
    print(f"\nScanning {len(files)} EU-tradeable coins "
          "(Binance signals -> OKX USDC execution)...")
    for n, path in enumerate(files, 1):
        if n % 50 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe[path.stem]
        df = pd.read_parquet(path)
        liq = float(df["quote_volume"].tail(24 * 30).median())
        if liq < C.MIN_USD_PER_H or len(df) < C.B_WINDOW_H + 200:
            continue
        if (now - df["open_time"].iloc[-1]).total_seconds() / 3600 > 26:
            stale += 1
            continue
        exec_info = {"kraken_pair": meta["exec_pair"],
                     "krk_24h": f"{meta.get('venue_usd_24h', 0)/1e6:,.2f}M"}

        # ---- B: fresh 30d-high breakout ----
        c = df["close"].reset_index(drop=True)
        ph = c.shift(1).rolling(C.B_WINDOW_H).max()
        cond = (c > ph).fillna(False).to_numpy()
        on = np.flatnonzero(cond & ~np.concatenate(([False], cond[:-1])))
        fresh = [int(i) for k, i in enumerate(on)
                 if (k == 0 or i - on[k - 1] >= C.B_MIN_GAP_H)
                 and i >= len(c) - FRESH_H]
        if fresh:
            b_rows.append({
                "coin": meta["symbol"], **exec_info, "rank": meta["rank"],
                "broke_h_ago": len(c) - 1 - fresh[-1],
                "above_old_high":
                    f"{float(c.iloc[-1] / ph.iloc[fresh[-1]] - 1):+.1%}",
            })

        # ---- W: fresh absorption crossing ----
        if not df["trades"].isna().all():
            dfw = add_accumulation(df)
            hot = (dfw["absorb"] >= C.W_SCORE_ALERT).fillna(False).to_numpy()
            cr = np.flatnonzero(hot & ~np.concatenate(([False], hot[:-1])))
            if len(cr) and cr[-1] >= len(dfw) - FRESH_H:
                w_rows.append({
                    "coin": meta["symbol"], **exec_info,
                    "rank": meta["rank"],
                    "crossed_h_ago": len(dfw) - 1 - int(cr[-1]),
                    "absorb_now": round(float(dfw["absorb"].iloc[-1]), 1)
                    if np.isfinite(dfw["absorb"].iloc[-1]) else None,
                })

        # ---- E: volume spikes z>=2 (watch) / z>=4 (trade), rank >= 76 ----
        if meta["rank"] >= C.E_MIN_RANK:
            dfb = F.add_baselines(df)
            win = dfb.iloc[-FRESH_H:]
            max_z = float(win["vol_z"].max())
            if max_z >= 2.0:
                move3h = float(dfb["close"].iloc[-1]
                               / dfb["close"].iloc[-4] - 1)
                silent = abs(move3h) < C.E_SILENT_MAX_MOVE_3H
                grade = ("z4 TRADE" if max_z >= C.E_MIN_Z else
                         "z3 watch" if max_z >= 3 else "z2 watch")
                e_rows.append({
                    "grade": grade,
                    "coin": meta["symbol"], **exec_info,
                    "rank": meta["rank"], "max_z_24h": round(max_z, 2),
                    "spike_h_ago": len(dfb) - 1 - int(win["vol_z"].idxmax()),
                    "move_3h": f"{move3h:+.1%}",
                    "silent": silent,
                })

    if stale:
        print(f"NOTE: {stale} coins stale - run ..\\fetch_data.py first.")

    for label, rows, sort in [
            ("E: volume spikes (z4+silent = trade tier; z2/z3 = watch)",
             e_rows, ("max_z_24h",)),
            ("W: fresh absorption crossings (7d holds, -25% stop)", w_rows,
             ("crossed_h_ago",)),
            ("B: fresh 30d-high breakouts (7d holds, -25% stop)", b_rows,
             ("broke_h_ago",))]:
        print(f"\n=== {label} ===")
        if rows:
            out = pd.DataFrame(rows)
            asc = [False] * len(sort) if sort[0] != "broke_h_ago" and \
                sort[0] != "crossed_h_ago" else [True]
            out = out.sort_values(list(sort), ascending=asc)
            print(out.to_string(index=False))
        else:
            print("none")

    all_rows = [dict(r, strategy=s) for s, rs in
                (("E", e_rows), ("W", w_rows), ("B", b_rows)) for r in rs]
    if all_rows:
        pd.DataFrame(all_rows).to_csv(C.OUT_DIR / "eu_watchlist.csv",
                                      index=False)
        print(f"\nSaved to {C.OUT_DIR / 'eu_watchlist.csv'}")
    print("\nExecute on the shown Kraken pair (maker orders - fees are "
          "the EU edge-killer).\nCheck krk_24h turnover before sizing; "
          "keep stakes <= ~1% of hourly volume.\nRe-validate on this "
          "universe first: python backtest_strategies.py. "
          "Not financial advice.")


if __name__ == "__main__":
    main()
