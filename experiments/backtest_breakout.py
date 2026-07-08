"""Backtest the 30d-high breakout as a full strategy candidate ("B").

Entry: close crosses above the prior 30-day high (first bar, 48h dedup,
one open trade per coin, liquidity >= $100k/h). Fixed variant menu:

  A_hold7d    buy the breakout close, hold 7 days, sell. 0.2% costs.
  B_disaster  same + wide -25% tail-insurance stop (the W lesson).
  C_ladder    TP +8%/+15% ladder + 7d time stop (expect this to LOSE to A:
              breakout profits live in the fat right tail).
  R_control   random-time entries, same coins/counts, 7d hold (beta check).

Credibility bar, pre-registered: A (or B) beats R_control in >= 5 of 6
half-years. Playbook stats said +3.1% edge; a real backtest with entry
timing, dedup, costs and control decides if it survives.

    python backtest_breakout.py     (run from the experiments folder)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))

import config as C                       # noqa: E402

OUT_DIR = HERE / "output"
MIN_USD_PER_H = 100_000
MIN_GAP_H = 48
HOLD_H = 168
COST = 0.002

VARIANTS = {
    "A_hold7d":   dict(tp=[], sl=None),
    "B_disaster": dict(tp=[], sl=-0.25),
    "C_ladder":   dict(tp=[(0.08, 0.5), (0.15, 0.5)], sl=None),
}


def simulate(df, i, entry, tp, sl):
    remaining, proceeds = 1.0, 0.0
    ladder = list(tp)
    end = min(i + HOLD_H, len(df) - 1)
    for j in range(i + 1, end + 1):
        lo, hi = df["low"].iloc[j], df["high"].iloc[j]
        if sl is not None and lo <= entry * (1 + sl):
            proceeds += remaining * entry * (1 + sl)
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


def breakout_onsets(df):
    c = df["close"]
    prior_high = c.shift(1).rolling(30 * 24).max()
    cond = (c > prior_high).fillna(False).to_numpy()
    on = np.flatnonzero(cond & ~np.concatenate(([False], cond[:-1])))
    keep, last = [], -MIN_GAP_H
    for i in on:
        if i - last >= MIN_GAP_H:
            keep.append(int(i))
            last = i
    return keep


def main():
    OUT_DIR.mkdir(exist_ok=True)
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    all_trades = {v: [] for v in VARIANTS}
    all_trades["R_control"] = []
    files = sorted(C.KLINES_DIR.glob("*.parquet"))
    print(f"Breakout backtest over {len(files)} coins...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        if path.stem not in universe:
            continue
        df = pd.read_parquet(path)
        if df["quote_volume"].tail(24 * 30).median() < MIN_USD_PER_H:
            continue
        ons = [i for i in breakout_onsets(df)
               if 24 * 35 <= i < len(df) - HOLD_H]
        if not ons:
            continue

        rng = np.random.default_rng(abs(hash(path.stem)) % 2**32)
        rand = np.sort(rng.integers(24 * 35, len(df) - HOLD_H - 1,
                                    len(ons) * 2))
        busy_until = -1
        for i in rand:
            if i <= busy_until:
                continue
            entry = float(df["close"].iloc[i])
            pnl, held = simulate(df, int(i), entry, [], None)
            busy_until = i + held
            all_trades["R_control"].append(
                {"pair": path.stem, "time": df["open_time"].iloc[int(i)],
                 "pnl": pnl - COST, "hours_held": held})

        for vname, v in VARIANTS.items():
            busy_until = -1
            for i in ons:
                if i <= busy_until:
                    continue
                entry = float(df["close"].iloc[i])
                pnl, held = simulate(df, i, entry, v["tp"], v["sl"])
                busy_until = i + held
                all_trades[vname].append(
                    {"pair": path.stem, "time": df["open_time"].iloc[i],
                     "pnl": pnl - COST, "hours_held": held})

    rows, per_period = [], {}
    for vname, trades in all_trades.items():
        if not trades:
            continue
        t = pd.DataFrame(trades)
        pnl = t["pnl"]
        eq = pnl.cumsum()
        w, l = pnl[pnl > 0], pnl[pnl <= 0]
        pf = float(w.sum() / -l.sum()) if l.sum() < 0 else float("inf")
        rows.append({
            "variant": vname, "n": len(t),
            "EV/trade": f"{pnl.mean():+.2%}",
            "win%": f"{(pnl > 0).mean():.0%}", "PF": round(pf, 2),
            "worst": f"{pnl.min():+.1%}",
            "total": f"{pnl.sum():+.1f}",
            "maxDD": f"{float((eq - eq.cummax()).min()):+.1f}",
        })
        t["period"] = (t["time"].dt.year.astype(str) + "-H"
                       + np.where(t["time"].dt.month <= 6, "1", "2"))
        per_period[vname] = t.groupby("period")["pnl"].agg(
            n="count", ev="mean").round(4)

    print("\n=== BREAKOUT VARIANTS (equal stake per trade) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n=== EV BY PERIOD ===")
    for vname, pp in per_period.items():
        print(f"\n{vname}:")
        print(pp.to_string())

    big = pd.concat([pd.DataFrame(tr).assign(variant=v)
                     for v, tr in all_trades.items() if tr])
    big.to_csv(OUT_DIR / "backtest_breakout.csv", index=False)
    print(f"\nTrades saved to {OUT_DIR / 'backtest_breakout.csv'}")
    print("Bar: A or B beats R_control in >= 5 of 6 half-years. "
          "Not financial advice.")


if __name__ == "__main__":
    main()
