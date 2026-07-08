"""Shared engine for the hold-duration experiments.

Same entry as the validated W strategy (fresh absorb >= 80 crossing),
plain hold-and-sell at each horizon, 0.2% costs, one open trade per coin.
Each horizon gets its own random-entry control (market beta grows with
hold time, so the control must too).

Run the wrappers, not this file:
    python sweep_1_7.py       days 1-7
    python sweep_8_14.py      days 8-14 (7d reference included)

NOTE: a parameter sweep is descriptive, not a selection tool. Read the
SHAPE of the curve (monotonic? plateau?). Cherry-picking the single best
horizon would be curve-fitting; the pre-registered 7d remains the strategy
unless the curve shows clear, consistent structure.
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


def collect(df, entries, horizon_h):
    """Plain hold trades with one-open-position-per-coin logic."""
    out, busy_until = [], -1
    c = df["close"]
    for i in entries:
        if i <= busy_until or i + horizon_h >= len(df):
            continue
        pnl = float(c.iloc[i + horizon_h] / c.iloc[i] - 1) - COST
        busy_until = i + horizon_h
        out.append((df["open_time"].iloc[i], pnl))
    return out


def main(horizons_d, tag):
    OUT_DIR.mkdir(exist_ok=True)
    with open(W.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    sig = {h: [] for h in horizons_d}
    ctl = {h: [] for h in horizons_d}
    files = sorted(W.KLINES_DIR.glob("*.parquet"))
    print(f"Hold-duration sweep over {len(files)} coins...")
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
        cross = cross[cross >= 24 * 14]
        if not len(cross):
            continue
        rng = np.random.default_rng(abs(hash(path.stem)) % 2**32)
        max_h = max(horizons_d) * 24
        rand = np.sort(rng.integers(24 * 14,
                                    max(len(df) - max_h - 1, 24 * 14 + 1),
                                    len(cross) * 2))
        for h_d in horizons_d:
            H = h_d * 24
            sig[h_d] += collect(df, cross, H)
            ctl[h_d] += collect(df, rand, H)

    rows = []
    excess_by_period = {}
    for h_d in horizons_d:
        s = pd.DataFrame(sig[h_d], columns=["time", "pnl"])
        r = pd.DataFrame(ctl[h_d], columns=["time", "pnl"])
        if not len(s):
            continue
        w_, l_ = s["pnl"][s["pnl"] > 0], s["pnl"][s["pnl"] <= 0]
        pf = float(w_.sum() / -l_.sum()) if l_.sum() < 0 else float("inf")
        rows.append({
            "hold_days": h_d, "n": len(s),
            "EV": f"{s['pnl'].mean():+.2%}",
            "win%": f"{(s['pnl'] > 0).mean():.0%}",
            "PF": round(pf, 2),
            "ctl_EV": f"{r['pnl'].mean():+.2%}",
            "excess": f"{s['pnl'].mean() - r['pnl'].mean():+.2%}",
            "EV_per_day": f"{s['pnl'].mean() / h_d:+.3%}",
        })
        for t_, label in ((s, "sig"), (r, "ctl")):
            t_["period"] = (t_["time"].dt.year.astype(str) + "-H"
                            + np.where(t_["time"].dt.month <= 6, "1", "2"))
        ev_s = s.groupby("period")["pnl"].mean()
        ev_r = r.groupby("period")["pnl"].mean()
        excess_by_period[f"{h_d}d"] = (ev_s - ev_r).round(4)

    print(f"\n=== HOLD DURATION SWEEP {tag} "
          "(entry: fresh absorb>=80 crossing) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n=== EXCESS EV (signal minus control) BY PERIOD ===")
    exp = pd.DataFrame(excess_by_period)
    print(exp.to_string())
    pd.DataFrame(rows).to_csv(OUT_DIR / f"hold_duration_{tag}.csv",
                              index=False)
    exp.to_csv(OUT_DIR / f"hold_duration_{tag}_by_period.csv")
    print(f"\nSaved to {OUT_DIR}")
    print("\nRead the curve, don't cherry-pick the peak: with "
          f"{len(horizons_d)} horizons tested, one will look best by "
          "chance. EV_per_day shows capital efficiency. "
          "Not financial advice.")
