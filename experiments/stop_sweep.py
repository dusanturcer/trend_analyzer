"""Stop-loss sweep for strategy W: what does tail insurance cost?

Same entries (fresh absorb >= 80 crossing), 7-day hold, 0.2% costs.
Stop levels: none, -30%, -25%, -20%, -15%, -12%, -10%, -8%, -5%.
Conservative fills: within a bar, the stop triggers before anything else.

For each level we price BOTH sides of the trade-off:
  cost side  : EV/trade, PF, % of trades stopped out
  safety side: worst trade, 5th-percentile trade, CVaR5 (mean of the
               worst 5%), max drawdown of the equity curve

    python stop_sweep.py     (run from the experiments folder)

Pre-registered reading rule: EV will fall as stops tighten (we know why).
The question is whether a WIDE stop exists whose EV cost is small
(< ~0.3%/trade) while meaningfully cutting the catastrophic tail
(hacks, delistings, -50% weeks). If every stop costs real EV, the honest
risk control is position sizing, not stops.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(PARENT / "whales"))

import wconfig as W                      # noqa: E402
from accumulation import add_accumulation  # noqa: E402

OUT_DIR = HERE / "output"
ENTRY_SCORE = 80
COST = 0.002
MIN_USD_PER_H = 100_000
HOLD_H = 168
STOPS = [None, -0.30, -0.25, -0.20, -0.15, -0.12, -0.10, -0.08, -0.05]


def simulate(df, i, entry, sl):
    end = min(i + HOLD_H, len(df) - 1)
    if sl is not None:
        stop_px = entry * (1 + sl)
        lows = df["low"].iloc[i + 1:end + 1]
        hit = lows[lows <= stop_px]
        if len(hit):
            j = int(hit.index[0])
            return sl, j - i, True
    return float(df["close"].iloc[end] / entry - 1), end - i, False


def main():
    OUT_DIR.mkdir(exist_ok=True)
    with open(W.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    trades = {s: [] for s in STOPS}
    files = sorted(W.KLINES_DIR.glob("*.parquet"))
    print(f"Stop-loss sweep over {len(files)} coins...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if meta is None or meta.get("exchange") == "okx":
            continue
        df = pd.read_parquet(path)
        if (df["quote_volume"].tail(24 * 30).median() < MIN_USD_PER_H
                or df["trades"].isna().all()):
            continue
        df = add_accumulation(df)
        hot = (df["absorb"] >= ENTRY_SCORE).fillna(False).to_numpy()
        cross = np.flatnonzero(hot & ~np.concatenate(([False], hot[:-1])))
        cross = cross[(cross >= 24 * 14) & (cross < len(df) - HOLD_H)]

        for sl in STOPS:
            busy_until = -1
            for i in cross:
                if i <= busy_until:
                    continue
                entry = float(df["close"].iloc[i])
                pnl, held, stopped = simulate(df, int(i), entry, sl)
                busy_until = i + held
                trades[sl].append(
                    {"time": df["open_time"].iloc[int(i)],
                     "pnl": pnl - COST, "stopped": stopped})

    rows = []
    for sl in STOPS:
        t = pd.DataFrame(trades[sl])
        if not len(t):
            continue
        pnl = t["pnl"]
        eq = pnl.cumsum()
        w_, l_ = pnl[pnl > 0], pnl[pnl <= 0]
        p5 = float(pnl.quantile(0.05))
        rows.append({
            "stop": "none" if sl is None else f"{sl:.0%}",
            "n": len(t),
            "EV": f"{pnl.mean():+.2%}",
            "win%": f"{(pnl > 0).mean():.0%}",
            "PF": round(float(w_.sum() / -l_.sum()), 2)
                  if l_.sum() < 0 else float("inf"),
            "stopped%": f"{t['stopped'].mean():.0%}",
            "worst": f"{pnl.min():+.1%}",
            "p5": f"{p5:+.1%}",
            "CVaR5": f"{pnl[pnl <= p5].mean():+.1%}",
            "maxDD": f"{float((eq - eq.cummax()).min()):+.1f}",
        })
    out = pd.DataFrame(rows)
    print("\n=== STOP-LOSS SWEEP (W entries, 7d hold) ===")
    print(out.to_string(index=False))
    out.to_csv(OUT_DIR / "stop_sweep.csv", index=False)

    # per-period EV for none vs the widest stops (regime robustness)
    print("\n=== EV BY PERIOD (insurance cost across regimes) ===")
    pp = {}
    for sl in [None, -0.30, -0.25, -0.20]:
        t = pd.DataFrame(trades[sl])
        t["period"] = (t["time"].dt.year.astype(str) + "-H"
                       + np.where(t["time"].dt.month <= 6, "1", "2"))
        pp["none" if sl is None else f"{sl:.0%}"] = \
            t.groupby("period")["pnl"].mean().round(4)
    print(pd.DataFrame(pp).to_string())
    print(f"\nSaved to {OUT_DIR / 'stop_sweep.csv'}")
    print("\nCompare each stop's EV against 'none': that difference is the "
          "insurance premium.\nThen check what it buys in worst/p5/CVaR5. "
          "Not financial advice.")


if __name__ == "__main__":
    main()
