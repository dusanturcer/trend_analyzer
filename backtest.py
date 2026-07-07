"""Backtest the playbook rules over all historical signals - variant menu.

Runs a FIXED, pre-defined set of strategy variants in one pass (not a
parameter search - keeps multiple-testing risk low):

  A baseline   TP +8%/+15%, SL -5%, 36h time stop, 0.5% costs, z>=3
  B maker      same, but 0.2% round-trip costs (maker/limit execution)
  C no-stop    no hard stop-loss, time stop only, 0.5% costs
  D strong-z   baseline but only z>=4 signals
  E combo      z>=4 + no stop-loss + 0.2% costs

    python backtest.py
"""
import json

import numpy as np
import pandas as pd

import config as C
import features as F

# ---- shared profile ----
BT_TIERS = {"mid", "small", "micro", "tiny"}
BT_MIN_USD_PER_H = 100_000
TIME_STOP_H = 36
ONE_TRADE_PER_COIN = True

VARIANTS = {
    "A_baseline": dict(min_z=3.0, tp=[(0.08, 0.5), (0.15, 0.5)],
                       sl=-0.05, cost=0.005),
    "B_maker":    dict(min_z=3.0, tp=[(0.08, 0.5), (0.15, 0.5)],
                       sl=-0.05, cost=0.002),
    "C_no_stop":  dict(min_z=3.0, tp=[(0.08, 0.5), (0.15, 0.5)],
                       sl=None, cost=0.005),
    "D_strong_z": dict(min_z=4.0, tp=[(0.08, 0.5), (0.15, 0.5)],
                       sl=-0.05, cost=0.005),
    "E_combo":    dict(min_z=4.0, tp=[(0.08, 0.5), (0.15, 0.5)],
                       sl=None, cost=0.002),
}


def tier_of(rank):
    return ("mega" if rank <= 20 else "large" if rank <= 75
            else "mid" if rank <= 150 else "small" if rank <= 200
            else "micro" if rank <= 350 else "tiny")


def simulate(df, i, entry, tp, sl):
    """Walk forward from bar i+1. Returns (pnl_before_costs, hours_held)."""
    remaining, proceeds = 1.0, 0.0
    ladder = list(tp)
    end = min(i + TIME_STOP_H, len(df) - 1)
    for j in range(i + 1, end + 1):
        lo, hi = df["low"].iloc[j], df["high"].iloc[j]
        # conservative: stop-loss checked first if both hit within the bar
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


def signals_for(df, min_z):
    ret3h = df["close"].pct_change(3).abs()
    raw = ((df["vol_z"] >= min_z) & (ret3h < 0.02)).to_numpy()
    first = raw & ~np.concatenate(([False], raw[:-1]))
    return np.flatnonzero(first)


def main():
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    all_trades = {v: [] for v in VARIANTS}
    files = sorted(C.KLINES_DIR.glob("*.parquet"))
    print(f"Backtesting {len(files)} coins x {len(VARIANTS)} variants...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if not meta or tier_of(meta["rank"]) not in BT_TIERS:
            continue
        df = pd.read_parquet(path)
        if df["quote_volume"].tail(24 * 30).median() < BT_MIN_USD_PER_H:
            continue
        df = F.add_baselines(df)

        sig_cache = {}
        for vname, v in VARIANTS.items():
            idx = sig_cache.setdefault(v["min_z"],
                                       signals_for(df, v["min_z"]))
            busy_until = -1
            for i in idx:
                if i < 24 * 7 or i + TIME_STOP_H >= len(df):
                    continue
                if ONE_TRADE_PER_COIN and i <= busy_until:
                    continue
                entry = float(df["close"].iloc[i])
                pnl, held = simulate(df, i, entry, v["tp"], v["sl"])
                busy_until = i + held
                all_trades[vname].append({
                    "pair": path.stem, "time": df["open_time"].iloc[i],
                    "vol_z": round(float(df["vol_z"].iloc[i]), 2),
                    "pnl": pnl - v["cost"], "hours_held": held,
                })

    rows, per_period = [], {}
    for vname, trades in all_trades.items():
        if not trades:
            continue
        t = pd.DataFrame(trades)
        t["variant"] = vname
        pnl = t["pnl"]
        equity = pnl.cumsum()
        wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
        rows.append({
            "variant": vname, "n": len(t),
            "EV/trade": f"{pnl.mean():+.2%}",
            "win%": f"{(pnl > 0).mean():.0%}",
            "PF": round(float(wins.sum() / -losses.sum()), 2)
                  if losses.sum() < 0 else float("inf"),
            "total": f"{pnl.sum():+.1f}",
            "maxDD": f"{float((equity - equity.cummax()).min()):+.1f}",
        })
        t["period"] = (t["time"].dt.year.astype(str) + "-H"
                       + np.where(t["time"].dt.month <= 6, "1", "2"))
        per_period[vname] = t.groupby("period")["pnl"].agg(
            n="count", ev="mean").round(4)

    print("\n=== VARIANT COMPARISON (equal stake per trade) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n=== EV BY PERIOD (robustness check: same sign everywhere?) ===")
    for vname, pp in per_period.items():
        print(f"\n{vname}:")
        print(pp.to_string())

    big = pd.concat([pd.DataFrame(tr).assign(variant=v)
                     for v, tr in all_trades.items() if tr])
    big.to_csv(C.OUT_DIR / "backtest_variants.csv", index=False)
    print("\nAll trades saved to output/backtest_variants.csv")
    print("NOTE: hourly-bar simulation, conservative fills. A variant is "
          "only credible if EV is positive in EVERY period, not just in "
          "total. Not financial advice.")


if __name__ == "__main__":
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
