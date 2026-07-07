"""Does the accumulation score actually predict anything?

For every coin and every 24th hour (to keep samples ~independent), bucket
the accumulation score and measure the NEXT 7 days: mean forward return
and P(>= +10%). If high-score buckets don't beat low ones, the whale
signature is folklore - at least in this form.

    python validate_whales.py
"""
import json

import numpy as np
import pandas as pd

import wconfig as W
from accumulation import add_accumulation


def main():
    with open(W.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    samples = []
    files = sorted(W.KLINES_DIR.glob("*.parquet"))
    print(f"Validating accumulation score over {len(files)} coins...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if meta is None or meta.get("exchange") == "okx":
            continue
        df = pd.read_parquet(path)
        if (df["quote_volume"].tail(24 * 30).median() < W.MIN_USD_PER_H
                or df["trades"].isna().all()):
            continue
        df = add_accumulation(df)
        c = df["close"]
        fwd_ret = c.shift(-W.FWD_HORIZON_H) / c - 1
        fwd_max = (c[::-1].rolling(W.FWD_HORIZON_H, min_periods=1)
                   .max()[::-1].shift(-1) / c - 1)
        idx = np.arange(24 * 14, len(df) - W.FWD_HORIZON_H, 24)
        s = pd.DataFrame({
            "pair": path.stem,
            "score": df["score"].iloc[idx].values,
            "absorb": df["absorb"].iloc[idx].values,
            "diverge": df["diverge"].iloc[idx].values,
            "fwd_ret": fwd_ret.iloc[idx].values,
            "fwd_max": fwd_max.iloc[idx].values,
            "time": df["open_time"].iloc[idx].values,
        }).dropna(subset=["fwd_ret"])
        samples.append(s)

    t = pd.concat(samples, ignore_index=True)
    t["good"] = t["fwd_max"] >= W.FWD_GOOD_RET
    print(f"\n{len(t)} samples across {t['pair'].nunique()} coins\n")

    for col, label in [("score", "v1 accumulation"), ("absorb", "v2 absorption")]:
        tv = t.dropna(subset=[col])
        if not len(tv):
            continue
        b = pd.cut(tv[col], [0, 20, 40, 60, 80, 101],
                   labels=["0-20", "20-40", "40-60", "60-80", "80+"])
        g = tv.groupby(b, observed=True).agg(
            n=("fwd_ret", "size"),
            mean_fwd_7d=("fwd_ret", "mean"),
            median_fwd_7d=("fwd_ret", "median"),
            p_plus10=("good", "mean"),
        ).round(4)
        print(f"Forward 7d outcome by {label} bucket:")
        print(g.to_string(), "\n")

    base = t["good"].mean()
    tt = pd.to_datetime(t["time"], utc=True)
    t["period"] = tt.dt.year.astype(str) + "-H" + np.where(
        tt.dt.month <= 6, "1", "2")

    for col, label in [("score", "v1 accumulation"), ("absorb", "v2 absorption")]:
        hot = t[t[col] >= W.SCORE_ALERT]
        if not len(hot):
            continue
        print(f"\n{label} >= {W.SCORE_ALERT}: P(+10% in 7d) = "
              f"{hot['good'].mean():.1%} (n={len(hot)}) vs base {base:.1%}"
              f" -> lift {hot['good'].mean() / base:.2f}x")
        print("  by period:", end=" ")
        parts = []
        for per, gp in t.groupby("period"):
            h = gp[gp[col] >= W.SCORE_ALERT]
            if len(h) >= 20:
                parts.append(f"{per}: {h['good'].mean() / gp['good'].mean():.2f}x"
                             f"(n={len(h)})")
        print("  ".join(parts))

    t.to_csv(W.OUT_DIR / "whale_validation_samples.csv", index=False)
    print(f"\nSamples saved to {W.OUT_DIR / 'whale_validation_samples.csv'}")
    print("Read it like the pump study: lift must be >1 in (nearly) every "
          "period to be real. Not financial advice.")


if __name__ == "__main__":
    W.OUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
