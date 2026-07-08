"""Factor study: which indicators predict upward moves, unconditionally?

Different question from e_combo/correlate.py (which asked "what improves
E-combo trades" - answer was nothing). Here we ask: across ALL coins and
ALL times, does any indicator rank tomorrow's/next week's winners?

Method: cross-sectional Information Coefficient (IC).
  - Sample every coin every 24h -> panel of (date, coin, indicators, fwd ret)
  - At each date, Spearman-rank-correlate indicator vs forward return
    ACROSS coins. This kills market-wide moves: we ask "did the indicator
    pick the RIGHT coins that day", not "did the market go up".
  - Aggregate: mean IC, t-stat over dates, % of dates positive,
    top-minus-bottom quintile spread, per-half-year mean IC.

    python factor_study.py     (run from the experiments folder)

Honesty: ~14 indicators x 3 horizons = ~40 tests. |t| > 3 AND stable sign
across periods AND a monotonic quintile spread = candidate. Anything less
is noise. Candidates must then survive out-of-sample before any use.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(PARENT / "e_combo"))

import config as C                        # noqa: E402
import features as F                      # noqa: E402
from indicators import add_indicators     # noqa: E402

OUT_DIR = HERE / "output"
MIN_USD_PER_H = 50_000
HORIZONS = {"fwd_1d": 24, "fwd_3d": 72, "fwd_7d": 168}
FACTORS = ["vol_z", "rsi14", "bbw_pctl", "dist_30d_high", "dist_30d_low",
           "obv_chg_pctl", "macd_rel", "atr_pctl", "vwap7_dist",
           "ret_7d", "ret_24h", "spike_hours_24h", "buy_ratio"]
MIN_COINS_XS = 15          # min coins per date for a cross-section


def build_panel():
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}
    frames = []
    files = sorted(C.KLINES_DIR.glob("*.parquet"))
    print(f"Building panel from {len(files)} coins...")
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
        for col, h in HORIZONS.items():
            df[col] = c.shift(-h) / c - 1
        idx = np.arange(24 * 35, len(df) - 168, 24)
        cols = ["open_time"] + FACTORS + list(HORIZONS)
        sub = df.iloc[idx][cols].copy()
        sub["date"] = sub["open_time"].dt.floor("D")
        sub["pair"] = path.stem
        frames.append(sub.drop(columns="open_time"))
    return pd.concat(frames, ignore_index=True)


def main(min_coins=MIN_COINS_XS):
    OUT_DIR.mkdir(exist_ok=True)
    panel = build_panel()
    print(f"panel: {len(panel):,} rows, {panel['pair'].nunique()} coins, "
          f"{panel['date'].nunique()} dates")

    rows = []
    for factor in FACTORS:
        for hcol in HORIZONS:
            ics, dates = [], []
            for d, g in panel.groupby("date"):
                gg = g[[factor, hcol]].dropna()
                if len(gg) < min_coins or gg[factor].nunique() < min_coins:
                    continue
                ic = stats.spearmanr(gg[factor], gg[hcol])[0]
                if ic == ic:
                    ics.append(ic)
                    dates.append(d)
            if len(ics) < 30:
                continue
            ics = pd.Series(ics, index=pd.DatetimeIndex(dates))
            t_stat = float(ics.mean() / ics.std() * np.sqrt(len(ics)))
            # quintile spread (pooled, demeaned per date)
            p = panel[[factor, hcol, "date"]].dropna()
            p["fw_dm"] = p[hcol] - p.groupby("date")[hcol].transform("mean")
            try:
                q = pd.qcut(p[factor], 5, labels=False, duplicates="drop")
                spread = float(p.loc[q == q.max(), "fw_dm"].mean()
                               - p.loc[q == 0, "fw_dm"].mean())
            except (ValueError, IndexError):
                spread = np.nan
            per = ics.groupby(ics.index.year.astype(str) + "-H"
                              + np.where(ics.index.month <= 6, "1", "2")
                              ).mean()
            stable = int((np.sign(per) == np.sign(ics.mean())).sum())
            rows.append({
                "factor": factor, "horizon": hcol.replace("fwd_", ""),
                "mean_IC": round(float(ics.mean()), 4),
                "t": round(t_stat, 1),
                "%pos_days": f"{(ics > 0).mean():.0%}",
                "Q5-Q1": f"{spread:+.2%}" if spread == spread else "n/a",
                "periods_same_sign": f"{stable}/{len(per)}",
            })

    if not rows:
        print("\nNo factor produced enough cross-sections - "
              "not enough coins/dates in the panel.")
        return
    out = (pd.DataFrame(rows)
           .assign(_a=lambda d: d["t"].abs())
           .sort_values("_a", ascending=False).drop(columns="_a"))
    print("\n=== CROSS-SECTIONAL FACTOR STUDY ===")
    print(out.to_string(index=False))
    out.to_csv(OUT_DIR / "factor_study.csv", index=False)

    sig = out[(out["t"].abs() >= 3)]
    print(f"\n{len(sig)} factor-horizon pairs at |t|>=3 "
          f"(of {len(out)} tested; expect ~{len(out) * 0.003:.1f} by chance "
          "at that bar)")
    print("Candidate = |t|>=3 AND all periods same sign AND monotonic "
          "spread. Must survive\nout-of-sample (future data) before any "
          "trading use. Not financial advice.")


if __name__ == "__main__":
    main()
