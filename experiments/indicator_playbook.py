"""Indicator playbook: what does each classic signal actually foreshadow?

For every coin over 3 years, find the ONSET of classic indicator states
(the moment the condition becomes true) and measure what happened in the
next 1, 3 and 7 days - versus the all-hours baseline of the same coins.

States tested (the trader's standard toolbox):
  rsi_oversold        RSI-14 crosses below 30
  rsi_overbought      RSI-14 crosses above 70
  bb_squeeze          Bollinger width drops into its tightest decile
  macd_bull_cross     MACD histogram flips negative -> positive
  macd_bear_cross     ...positive -> negative
  golden_cross        50d SMA crosses above 200d SMA
  death_cross         50d SMA crosses below 200d SMA
  breakout_30d_high   close breaks above the prior 30d high
  breakdown_30d_low   close breaks below the prior 30d low
  capitulation        -10% or worse in 24h
  euphoria            +10% or better in 24h
  vol_spike_z3        volume z-score >= 3 (any kind, not just silent)
  obv_bull_div        price down >2% over 7d while OBV change in top 30%

    python indicator_playbook.py     (run from the experiments folder)

Onsets are deduplicated (48h min gap per state per coin). Read `edge_7d`
(mean 7d return minus baseline) together with `n`, `stable` (half-years
where the edge kept its sign) and P(+10%). ~13 states x 3 horizons: at
least one row will look good by chance - trust stability, not peaks.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(PARENT / "e_combo"))

import config as C                        # noqa: E402
import features as F                      # noqa: E402
from indicators import add_indicators     # noqa: E402

OUT_DIR = HERE / "output"
MIN_USD_PER_H = 50_000
MIN_GAP_H = 48
HORIZONS = {"1d": 24, "3d": 72, "7d": 168}


def onsets(cond: pd.Series) -> np.ndarray:
    c = cond.fillna(False).to_numpy()
    on = np.flatnonzero(c & ~np.concatenate(([False], c[:-1])))
    keep, last = [], -MIN_GAP_H
    for i in on:
        if i - last >= MIN_GAP_H:
            keep.append(i)
            last = i
    return np.array(keep, dtype=int)


def state_conditions(df: pd.DataFrame) -> dict:
    c = df["close"]
    sma50 = c.rolling(50 * 24).mean()
    sma200 = c.rolling(200 * 24).mean()
    prior_high = c.shift(1).rolling(30 * 24).max()
    prior_low = c.shift(1).rolling(30 * 24).min()
    return {
        "rsi_oversold": df["rsi14"] < 30,
        "rsi_overbought": df["rsi14"] > 70,
        "bb_squeeze": df["bbw_pctl"] < 10,
        "macd_bull_cross": (df["macd_rel"] > 0) & (df["macd_rel"].shift(1) <= 0),
        "macd_bear_cross": (df["macd_rel"] < 0) & (df["macd_rel"].shift(1) >= 0),
        "golden_cross": (sma50 > sma200) & (sma50.shift(1) <= sma200.shift(1)),
        "death_cross": (sma50 < sma200) & (sma50.shift(1) >= sma200.shift(1)),
        "breakout_30d_high": c > prior_high,
        "breakdown_30d_low": c < prior_low,
        "capitulation": df["ret_24h"] < -0.10,
        "euphoria": df["ret_24h"] > 0.10,
        "vol_spike_z3": df["vol_z"] >= 3,
        "obv_bull_div": (df["ret_7d"] < -0.02) & (df["obv_chg_pctl"] > 70),
    }


def main():
    OUT_DIR.mkdir(exist_ok=True)
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    events = {}          # state -> list of (time, fwd1, fwd3, fwd7, fwdmax7)
    baseline = []        # sampled all-hours rows
    files = sorted(C.KLINES_DIR.glob("*.parquet"))
    print(f"Scanning {len(files)} coins for indicator states...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        if path.stem not in universe:
            continue
        df = pd.read_parquet(path)
        if df["quote_volume"].tail(24 * 30).median() < MIN_USD_PER_H:
            continue
        df = add_indicators(F.add_baselines(df))
        c = df["close"]
        fwd = {k: (c.shift(-h) / c - 1) for k, h in HORIZONS.items()}
        fwd_max7 = (c[::-1].rolling(168, min_periods=1).max()[::-1]
                    .shift(-1) / c - 1)

        lo, hi = 24 * 35, len(df) - 169
        for b in np.arange(lo, hi, 24):
            baseline.append((df["open_time"].iloc[b],
                             *(float(fwd[k].iloc[b]) for k in HORIZONS),
                             float(fwd_max7.iloc[b])))
        for state, cond in state_conditions(df).items():
            for i in onsets(cond):
                if i < lo or i >= hi:
                    continue
                events.setdefault(state, []).append(
                    (df["open_time"].iloc[int(i)],
                     *(float(fwd[k].iloc[int(i)]) for k in HORIZONS),
                     float(fwd_max7.iloc[int(i)])))

    cols = ["time", "f1", "f3", "f7", "fmax7"]
    base = pd.DataFrame(baseline, columns=cols)
    b1, b3, b7 = base["f1"].mean(), base["f3"].mean(), base["f7"].mean()
    bp10 = (base["fmax7"] >= 0.10).mean()
    bup = (base["f7"] > 0).mean()
    print(f"\nBaseline (all hours, n={len(base):,}): "
          f"1d {b1:+.2%}  3d {b3:+.2%}  7d {b7:+.2%}  "
          f"P(up,7d) {bup:.0%}  P(+10% in 7d) {bp10:.0%}")

    rows = []
    for state, ev in sorted(events.items()):
        t = pd.DataFrame(ev, columns=cols)
        if len(t) < 50:
            continue
        t["period"] = (t["time"].dt.year.astype(str) + "-H"
                       + np.where(t["time"].dt.month <= 6, "1", "2"))
        edge7 = t["f7"].mean() - b7
        per = t.groupby("period")["f7"].mean() - b7
        rows.append({
            "state": state, "n": len(t),
            "ret_1d": f"{t['f1'].mean():+.2%}",
            "ret_3d": f"{t['f3'].mean():+.2%}",
            "ret_7d": f"{t['f7'].mean():+.2%}",
            "edge_7d": f"{edge7:+.2%}",
            "P(up7d)": f"{(t['f7'] > 0).mean():.0%}",
            "P(+10%)": f"{(t['fmax7'] >= 0.10).mean():.0%}",
            "stable": f"{int((np.sign(per) == np.sign(edge7)).sum())}/{len(per)}",
            "_e": edge7,
        })
    out = (pd.DataFrame(rows).sort_values("_e", ascending=False)
           .drop(columns="_e"))
    print("\n=== INDICATOR PLAYBOOK (vs baseline, next 7 days) ===")
    print(out.to_string(index=False))
    out.to_csv(OUT_DIR / "indicator_playbook.csv", index=False)
    print(f"\nSaved to {OUT_DIR / 'indicator_playbook.csv'}")
    print("\nedge_7d = mean 7d return minus the all-hours baseline. "
          "'stable' = half-years\nwhere the edge kept its sign. Advice-grade "
          "= |edge| meaningful AND stable >= 5/7\nAND n >= 200. These are "
          "context stats, not backtested strategies (no costs,\nno entry "
          "timing). Not financial advice.")


if __name__ == "__main__":
    main()
