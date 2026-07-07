"""Backtest ONLY the E-combo strategy, attaching all indicators to every
trade so correlate.py can find what separates winners from losers.

    python backtest_e.py       (run from the e_combo folder)

Writes output/e_trades.csv and prints the headline stats.
"""
import json

import numpy as np
import pandas as pd

import econfig as E          # also puts parent on sys.path
import features as F         # parent module
from indicators import add_indicators, INDICATOR_COLS


def simulate(df, i, entry):
    remaining, proceeds = 1.0, 0.0
    ladder = list(E.TP_LADDER)
    end = min(i + E.TIME_STOP_H, len(df) - 1)
    for j in range(i + 1, end + 1):
        lo, hi = df["low"].iloc[j], df["high"].iloc[j]
        if E.STOP_LOSS is not None and lo <= entry * (1 + E.STOP_LOSS):
            proceeds += remaining * entry * (1 + E.STOP_LOSS)
            return proceeds / entry - 1, j - i
        while ladder and hi >= entry * (1 + ladder[0][0]):
            level, frac = ladder.pop(0)
            sell = min(frac, remaining)
            proceeds += sell * entry * (1 + level)
            remaining -= sell
            if remaining <= 1e-9:
                return proceeds / entry - 1, j - i
    proceeds += remaining * df["close"].iloc[end]
    return proceeds / entry - 1, end - i


def main():
    E.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(E.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    btc = None
    for name in ("BTCUSDT.parquet",):
        p = E.KLINES_DIR / name
        if p.exists():
            btc = pd.read_parquet(p)[["open_time", "close"]]

    trades = []
    files = sorted(E.KLINES_DIR.glob("*.parquet"))
    print(f"E-combo backtest over {len(files)} coins "
          f"(z>={E.MIN_Z}, no SL, {E.COST_ROUNDTRIP:.1%} costs)...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if not meta or E.tier_of(meta["rank"]) not in E.TIERS:
            continue
        df = pd.read_parquet(path)
        if df["quote_volume"].tail(24 * 30).median() < E.MIN_USD_PER_H:
            continue
        df = add_indicators(F.add_baselines(df))

        ret3h = df["close"].pct_change(3).abs()
        raw = ((df["vol_z"] >= E.MIN_Z)
               & (ret3h < E.SILENT_MAX_MOVE_3H)).to_numpy()
        firsts = raw & ~np.concatenate(([False], raw[:-1]))
        busy_until = -1
        for i in np.flatnonzero(firsts):
            if i < 24 * 7 or i + E.TIME_STOP_H >= len(df):
                continue
            if E.ONE_TRADE_PER_COIN and i <= busy_until:
                continue
            entry = float(df["close"].iloc[i])
            pnl, held = simulate(df, i, entry)
            busy_until = i + held
            row = {"pair": path.stem, "tier": E.tier_of(meta["rank"]),
                   "time": df["open_time"].iloc[i],
                   "vol_z": round(float(df["vol_z"].iloc[i]), 2),
                   "pnl": pnl - E.COST_ROUNDTRIP,
                   "win": pnl - E.COST_ROUNDTRIP > 0,
                   "hours_held": held}
            for col in INDICATOR_COLS:
                row[col] = float(df[col].iloc[i]) if col in df else np.nan
            # market context: BTC 24h return at signal time
            if btc is not None:
                k = btc["open_time"].searchsorted(row["time"])
                row["btc_ret_24h"] = (float(btc["close"].iloc[k - 1]
                                      / btc["close"].iloc[k - 25] - 1)
                                      if 25 <= k <= len(btc) else np.nan)
            trades.append(row)

    if not trades:
        print("No trades found - is ../data populated?")
        return
    t = pd.DataFrame(trades)
    t.to_csv(E.OUT_DIR / "e_trades.csv", index=False)

    pnl = t["pnl"]
    eq = pnl.cumsum()
    w, l = pnl[pnl > 0], pnl[pnl <= 0]
    t["period"] = (t["time"].dt.year.astype(str) + "-H"
                   + np.where(t["time"].dt.month <= 6, "1", "2"))
    print(f"\n=== E-combo: {len(t)} trades ===")
    pf = w.sum() / -l.sum() if l.sum() < 0 else float("inf")
    print(f"EV/trade: {pnl.mean():+.2%}  win: {(pnl > 0).mean():.0%}  "
          f"PF: {pf:.2f}  "
          f"maxDD: {float((eq - eq.cummax()).min()):+.1f} stakes")
    print(t.groupby("period")["pnl"].agg(n="count", ev="mean")
          .round(4).to_string())
    print(f"\nTrades + indicators saved to {E.OUT_DIR / 'e_trades.csv'}")
    print("Next: python correlate.py")


if __name__ == "__main__":
    main()
