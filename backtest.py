"""Backtest the playbook rules over all historical signals.

Simulates: entry at the close of each silent-spike signal bar (profile:
z >= BT_MIN_Z, tiers mid & below, liquid pairs), take-profit ladder,
hard stop-loss, time stop. Reports expected value per trade AFTER costs,
win rate, drawdown, and breakdowns by period / spike strength.

    python backtest.py
"""
import json

import numpy as np
import pandas as pd

import config as C
import features as F

# ---- strategy parameters (edit to taste, then re-run) ----
BT_MIN_Z = 3.0
BT_TIERS = {"mid", "small", "micro", "tiny"}
BT_MIN_USD_PER_H = 100_000
TP_LADDER = [(0.08, 0.5), (0.15, 0.5)]   # (gain level, fraction to sell)
STOP_LOSS = -0.05
TIME_STOP_H = 36
COST_ROUNDTRIP = 0.005                    # fees+slippage both ways (0.5%)
ONE_TRADE_PER_COIN = True                 # skip signal if a trade is open


def tier_of(rank):
    return ("mega" if rank <= 20 else "large" if rank <= 75
            else "mid" if rank <= 150 else "small" if rank <= 200
            else "micro" if rank <= 350 else "tiny")


def simulate(df, i, entry):
    """Walk forward from bar i+1. Returns (pnl_before_costs, hours_held)."""
    remaining, proceeds = 1.0, 0.0
    ladder = list(TP_LADDER)
    end = min(i + TIME_STOP_H, len(df) - 1)
    for j in range(i + 1, end + 1):
        lo, hi = df["low"].iloc[j], df["high"].iloc[j]
        # conservative: stop-loss checked first if both hit within the bar
        if lo <= entry * (1 + STOP_LOSS):
            proceeds += remaining * entry * (1 + STOP_LOSS)
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
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    trades = []
    files = sorted(C.KLINES_DIR.glob("*.parquet"))
    print(f"Backtesting {len(files)} coins "
          f"(profile: z>={BT_MIN_Z}, {sorted(BT_TIERS)}, "
          f">=${BT_MIN_USD_PER_H:,}/h, costs {COST_ROUNDTRIP:.1%})...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        pair = path.stem
        meta = universe.get(pair)
        if not meta or tier_of(meta["rank"]) not in BT_TIERS:
            continue
        df = pd.read_parquet(path)
        if df["quote_volume"].tail(24 * 30).median() < BT_MIN_USD_PER_H:
            continue
        df = F.add_baselines(df)

        ret3h = df["close"].pct_change(3).abs()
        spike_raw = ((df["vol_z"] >= BT_MIN_Z) & (ret3h < 0.02)).to_numpy()
        spike = spike_raw & ~np.concatenate(([False], spike_raw[:-1]))
        busy_until = -1
        for i in np.flatnonzero(spike):
            if i < 24 * 7 or i + TIME_STOP_H >= len(df):
                continue
            if ONE_TRADE_PER_COIN and i <= busy_until:
                continue
            entry = float(df["close"].iloc[i])
            pnl, held = simulate(df, i, entry)
            busy_until = i + held
            trades.append({
                "pair": pair, "tier": tier_of(meta["rank"]),
                "time": df["open_time"].iloc[i],
                "vol_z": round(float(df["vol_z"].iloc[i]), 2),
                "pnl": pnl - COST_ROUNDTRIP, "hours_held": held,
            })

    if not trades:
        print("No trades matched the profile.")
        return
    t = pd.DataFrame(trades)
    t.to_csv(C.OUT_DIR / "backtest_trades.csv", index=False)

    pnl = t["pnl"]
    equity = pnl.cumsum()  # equal stake per trade, in "stakes" units
    dd = float((equity - equity.cummax()).min())
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")

    print(f"\n=== {len(t)} trades, "
          f"{t['time'].min():%Y-%m}..{t['time'].max():%Y-%m} ===")
    print(f"EV per trade (after costs): {pnl.mean():+.2%}")
    print(f"median: {pnl.median():+.2%}   win rate: {(pnl > 0).mean():.0%}")
    print(f"avg win {wins.mean():+.2%} / avg loss {losses.mean():+.2%}   "
          f"profit factor: {pf:.2f}")
    print(f"total return: {pnl.sum():+.1f} stakes   "
          f"max drawdown: {dd:+.1f} stakes")
    print(f"avg hold: {t['hours_held'].mean():.0f}h")

    t["period"] = (t["time"].dt.year.astype(str) + "-H"
                   + np.where(t["time"].dt.month <= 6, "1", "2"))
    print("\nEV by period:")
    print(t.groupby("period")["pnl"].agg(n="count", ev="mean")
          .round(4).to_string())
    t["zbin"] = pd.cut(t["vol_z"], [3, 4, 99])
    print("\nEV by spike strength:")
    print(t.groupby("zbin", observed=True)["pnl"]
          .agg(n="count", ev="mean").round(4).to_string())
    print("\nTrades saved to output/backtest_trades.csv")
    print("NOTE: hourly-bar simulation with conservative fills; "
          "real results will differ. Not financial advice.")


if __name__ == "__main__":
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
