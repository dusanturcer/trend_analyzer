"""Backtest the absorption signal (v2) with real trading rules.

Entry: the hour a coin's absorption score first crosses >= 80
       (heavy taker selling absorbed without price falling).
Fixed variant menu (pre-defined, not searched):

  A ladder   sell half +8%, half +15%, 7d time stop, no SL, 0.2% costs
  B stopped  same but hard stop-loss -8%
  C hold7d   plain 7-day hold, no TP (what the raw stats implied)

Conservative fills: stop checked before TP within each bar.

    python backtest_w.py
"""
import json

import numpy as np
import pandas as pd

import wconfig as W
from accumulation import add_accumulation

TRADE_MIN_USD_PER_H = 100_000     # stricter than the watch floor
ENTRY_SCORE = 80                  # = W.SCORE_ALERT, frozen for the backtest
TIME_STOP_H = 168                 # 7 days, matching the validated horizon
ONE_TRADE_PER_COIN = True

VARIANTS = {
    "A_ladder":  dict(tp=[(0.08, 0.5), (0.15, 0.5)], sl=None,  cost=0.002),
    "B_stopped": dict(tp=[(0.08, 0.5), (0.15, 0.5)], sl=-0.08, cost=0.002),
    "C_hold7d":  dict(tp=[],                          sl=None,  cost=0.002),
}


def simulate(df, i, entry, tp, sl):
    remaining, proceeds = 1.0, 0.0
    ladder = list(tp)
    end = min(i + TIME_STOP_H, len(df) - 1)
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


def main():
    W.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(W.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    all_trades = {v: [] for v in VARIANTS}
    all_trades["R_control"] = []
    files = sorted(W.KLINES_DIR.glob("*.parquet"))
    print(f"Absorption backtest over {len(files)} coins, "
          f"entry: absorb >= {ENTRY_SCORE} crossing...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if meta is None or meta.get("exchange") == "okx":
            continue
        df = pd.read_parquet(path)
        if (df["quote_volume"].tail(24 * 30).median() < TRADE_MIN_USD_PER_H
                or df["trades"].isna().all()):
            continue
        df = add_accumulation(df)

        hot = (df["absorb"] >= ENTRY_SCORE).fillna(False).to_numpy()
        crossings = np.flatnonzero(hot & ~np.concatenate(([False], hot[:-1])))

        # market-beta control: same coin, same number of trades, same
        # 7d-hold rules - but at RANDOM times. If absorption entries don't
        # beat this, the signal is just market exposure.
        rng = np.random.default_rng(abs(hash(path.stem)) % 2**32)
        lo_i, hi_i = 24 * 14, len(df) - TIME_STOP_H - 1
        n_valid = sum(1 for i in crossings if lo_i <= i < hi_i)
        if hi_i > lo_i and n_valid:
            busy_until = -1
            for i in sorted(rng.integers(lo_i, hi_i, n_valid * 2)):
                if ONE_TRADE_PER_COIN and i <= busy_until:
                    continue
                entry = float(df["close"].iloc[i])
                pnl, held = simulate(df, int(i), entry, [], None)
                busy_until = i + held
                all_trades["R_control"].append({
                    "pair": path.stem, "time": df["open_time"].iloc[int(i)],
                    "absorb": np.nan, "pnl": pnl - 0.002,
                    "hours_held": held,
                })

        for vname, v in VARIANTS.items():
            busy_until = -1
            for i in crossings:
                if i < 24 * 14 or i + TIME_STOP_H >= len(df):
                    continue
                if ONE_TRADE_PER_COIN and i <= busy_until:
                    continue
                entry = float(df["close"].iloc[i])
                pnl, held = simulate(df, i, entry, v["tp"], v["sl"])
                busy_until = i + held
                all_trades[vname].append({
                    "pair": path.stem, "time": df["open_time"].iloc[i],
                    "absorb": round(float(df["absorb"].iloc[i]), 1),
                    "pnl": pnl - v["cost"], "hours_held": held,
                })

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
            "total": f"{pnl.sum():+.1f}",
            "maxDD": f"{float((eq - eq.cummax()).min()):+.1f}",
            "avg_h": round(float(t['hours_held'].mean())),
        })
        t["period"] = (t["time"].dt.year.astype(str) + "-H"
                       + np.where(t["time"].dt.month <= 6, "1", "2"))
        per_period[vname] = t.groupby("period")["pnl"].agg(
            n="count", ev="mean").round(4)

    print("\n=== ABSORPTION VARIANTS (equal stake per trade) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n=== EV BY PERIOD ===")
    for vname, pp in per_period.items():
        print(f"\n{vname}:")
        print(pp.to_string())

    big = pd.concat([pd.DataFrame(tr).assign(variant=v)
                     for v, tr in all_trades.items() if tr])
    big.to_csv(W.OUT_DIR / "backtest_w_trades.csv", index=False)
    print(f"\nTrades saved to {W.OUT_DIR / 'backtest_w_trades.csv'}")
    print("Credibility bar: EV positive in (nearly) every period. This is "
          "the 2nd hypothesis tested on this data - treat marginal results "
          "as noise. Not financial advice.")


if __name__ == "__main__":
    main()
