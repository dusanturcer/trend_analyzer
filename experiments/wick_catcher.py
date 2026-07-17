"""Wick-catcher backtest: can resting bids harvest stop-hunt overshoots?

Thesis (pre-registered): stop cascades overshoot fair price; a standing
maker bid X% below market gets filled by the wick and profits from the
snap-back. The passive version of "buy the sweep".

Rules, fixed before looking at results:
  - Bid is re-placed every hour at X% below the last close.
  - Fill: next hour's low trades through the bid (entry AT the bid, maker).
  - Exit: TP limit at +Y% over entry, else time stop at 48h, with a -25%
    disaster stop checked first within each bar (conservative).
  - One open trade per coin. Costs 0.2% RT (parent Binance assumption).

Variant menu (depth X / TP Y):  A: 5%/3%   B: 8%/5%   C: 12%/8%
Control: random-hour MARKET entries (same coin, same trade count, same
exit rules). The strategy's whole claim is the entry discount - so it
must beat identical exits with random timing.

Bar: EV > 0 after costs AND beats control in (nearly) every half-year.
Known risk: in trending-down regimes the wick keeps going (knife-catch).

    python wick_catcher.py     (run from the experiments folder)
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
HOLD_MAX_H = 48
COST = 0.002
DISASTER = -0.25
VARIANTS = {"A_5pct": (0.05, 0.03),
            "B_8pct": (0.08, 0.05),
            "C_12pct": (0.12, 0.08)}


def exit_trade(df, i, entry, tp):
    """From bar i+1 (bar i is the fill bar): disaster stop first, then TP,
    else close at time stop. Returns (pnl_before_costs, hours_held)."""
    end = min(i + HOLD_MAX_H, len(df) - 1)
    for j in range(i + 1, end + 1):
        if df["low"].iloc[j] <= entry * (1 + DISASTER):
            return DISASTER, j - i
        if df["high"].iloc[j] >= entry * (1 + tp):
            return tp, j - i
    return float(df["close"].iloc[end] / entry - 1), end - i


def run_side(df, entries_kind, depth, tp, rng=None, n_target=None):
    """entries_kind: 'wick' (limit fills) or 'random' (market entries)."""
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    trades = []
    lo_i = 24 * 35
    if entries_kind == "wick":
        bid = close[:-1] * (1 - depth)
        hit = np.flatnonzero(low[1:] <= bid * 0.999) + 1  # fill bar index
        busy = -1
        for i in hit:
            if i <= busy or i < lo_i or i + HOLD_MAX_H >= len(close):
                continue
            entry = float(bid[i - 1])
            pnl, held = exit_trade(df, int(i), entry, tp)
            busy = i + held
            trades.append((df["open_time"].iloc[int(i)], pnl - COST, held))
    else:
        hi_i = len(close) - HOLD_MAX_H - 1
        if not n_target or hi_i <= lo_i:
            return trades
        idx = np.sort(rng.integers(lo_i, hi_i, n_target * 2))
        busy = -1
        for i in idx:
            if len(trades) >= n_target:
                break
            if i <= busy:
                continue
            entry = float(close[i])
            pnl, held = exit_trade(df, int(i), entry, tp)
            busy = i + held
            trades.append((df["open_time"].iloc[int(i)], pnl - COST, held))
    return trades


def main():
    OUT_DIR.mkdir(exist_ok=True)
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    buckets = {}
    files = sorted(C.KLINES_DIR.glob("*.parquet"))
    print(f"Wick-catcher backtest over {len(files)} coins...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        if path.stem not in universe:
            continue
        df = pd.read_parquet(path)
        if df["quote_volume"].tail(24 * 30).median() < MIN_USD_PER_H:
            continue
        rng = np.random.default_rng(abs(hash(path.stem)) % 2**32)
        for vname, (depth, tp) in VARIANTS.items():
            t_w = run_side(df, "wick", depth, tp)
            buckets.setdefault(vname, []).extend(
                dict(pair=path.stem, time=a, pnl=b, held=c)
                for a, b, c in t_w)
            t_r = run_side(df, "random", depth, tp, rng=rng,
                           n_target=len(t_w))
            buckets.setdefault(vname + "_ctl", []).extend(
                dict(pair=path.stem, time=a, pnl=b, held=c)
                for a, b, c in t_r)

    rows, pp = [], {}
    for name, trades in buckets.items():
        if not trades:
            continue
        t = pd.DataFrame(trades)
        pnl = t["pnl"]
        eq = pnl.cumsum()
        w, l = pnl[pnl > 0], pnl[pnl <= 0]
        pf = float(w.sum() / -l.sum()) if l.sum() < 0 else float("inf")
        rows.append({"variant": name, "n": len(t),
                     "EV/trade": f"{pnl.mean():+.2%}",
                     "win%": f"{(pnl > 0).mean():.0%}",
                     "PF": round(pf, 2),
                     "worst": f"{pnl.min():+.1%}",
                     "maxDD": f"{float((eq - eq.cummax()).min()):+.1f}",
                     "avg_h": round(float(t['held'].mean()))})
        t["period"] = (t["time"].dt.year.astype(str) + "-H"
                       + np.where(t["time"].dt.month <= 6, "1", "2"))
        pp[name] = t.groupby("period")["pnl"].agg(n="count", ev="mean")\
            .round(4)

    print("\n=== WICK CATCHER (resting bids vs random-time market entries) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n=== EV BY PERIOD ===")
    for name in VARIANTS:
        for suffix in ("", "_ctl"):
            key = name + suffix
            if key in pp:
                print(f"\n{key}:")
                print(pp[key].to_string())

    big = pd.concat([pd.DataFrame(tr).assign(variant=k)
                     for k, tr in buckets.items() if tr])
    big.to_csv(OUT_DIR / "wick_catcher.csv", index=False)
    print(f"\nTrades saved to {OUT_DIR / 'wick_catcher.csv'}")
    print("Bar: EV>0 AND beats control in (nearly) every half-year. "
          "Watch the down-regime\nperiods (2025-H1) - that's where knife-"
          "catching dies. Not financial advice.")


if __name__ == "__main__":
    main()
