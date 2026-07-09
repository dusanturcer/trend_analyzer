"""Backtest strategies E, W and B on the EUROPE universe (Binance candles,
restricted to coins tradeable on OKX with USDC pairs).

The full-universe numbers do NOT transfer automatically: this universe is
biased toward larger, OKX-listed coins - E-combo's edge in particular came
disproportionately from small caps. Bar, as always: live beats its random
control in (nearly) every half-year.

    python backtest_strategies.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))
sys.path.insert(2, str(HERE.parent / "whales"))

import config as C          # noqa: E402  (europe)
import features as F        # noqa: E402
from accumulation import add_accumulation  # noqa: E402


def simulate(df, i, entry, tp, sl, hold_h):
    remaining, proceeds = 1.0, 0.0
    ladder = list(tp)
    end = min(i + hold_h, len(df) - 1)
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


def dedup(idx, gap):
    keep, last = [], -gap
    for i in idx:
        if i - last >= gap:
            keep.append(int(i))
            last = i
    return keep


def run(entries, df, tp, sl, hold_h, bucket, pair):
    busy = -1
    for i in entries:
        if i <= busy or i + hold_h >= len(df):
            continue
        entry = float(df["close"].iloc[i])
        pnl, held = simulate(df, i, entry, tp, sl, hold_h)
        busy = i + held
        bucket.append({"pair": pair, "time": df["open_time"].iloc[i],
                       "pnl": pnl - C.COST_ROUNDTRIP})


def onset_idx(cond, lo):
    raw = cond.fillna(False).to_numpy()
    on = np.flatnonzero(raw & ~np.concatenate(([False], raw[:-1])))
    return [int(i) for i in on if i >= lo]


def main():
    with open(C.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    names = ["E_live", "E_control", "W_live", "W_control",
             "B_live", "B_control"]
    buckets = {k: [] for k in names}
    files = [p for p in sorted(C.KLINES_DIR.glob("*.parquet"))
             if p.stem in universe]
    print(f"EU backtest (E+W+B) over {len(files)} coins "
          "(Binance candles, OKX-USDC-tradeable universe)...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe[path.stem]
        df = pd.read_parquet(path)
        if df["quote_volume"].tail(24 * 30).median() < C.MIN_USD_PER_H:
            continue
        rng = np.random.default_rng(abs(hash(path.stem)) % 2**32)
        lo = 24 * 35

        # ---- B: 30d-high breakout ----
        c = df["close"].reset_index(drop=True)
        ph = c.shift(1).rolling(C.B_WINDOW_H).max()
        ons = dedup(onset_idx(c > ph, lo), C.B_MIN_GAP_H)
        if ons:
            run(ons, df, [], C.B_DISASTER_STOP, C.B_HOLD_H,
                buckets["B_live"], path.stem)
            rand = np.sort(rng.integers(
                lo, max(len(df) - C.B_HOLD_H - 1, lo + 1), len(ons) * 2))
            run(rand, df, [], None, C.B_HOLD_H,
                buckets["B_control"], path.stem)

        # ---- W: absorption crossing ----
        if not df["trades"].isna().all():
            dfw = add_accumulation(df)
            ons = onset_idx(dfw["absorb"] >= C.W_SCORE_ALERT, max(lo, 24 * 14))
            if ons:
                run(ons, dfw, [], C.W_DISASTER_STOP, C.W_HOLD_H,
                    buckets["W_live"], path.stem)
                rand = np.sort(rng.integers(
                    lo, max(len(df) - C.W_HOLD_H - 1, lo + 1), len(ons) * 2))
                run(rand, dfw, [], None, C.W_HOLD_H,
                    buckets["W_control"], path.stem)

        # ---- E: silent z>=4 spike, rank >= 76 ----
        if meta["rank"] >= C.E_MIN_RANK:
            dfb = F.add_baselines(df)
            ret3h = dfb["close"].pct_change(3).abs()
            ons = onset_idx((dfb["vol_z"] >= C.E_MIN_Z)
                            & (ret3h < C.E_SILENT_MAX_MOVE_3H), lo)
            if ons:
                run(ons, dfb, C.E_TP_LADDER, None, C.E_TIME_STOP_H,
                    buckets["E_live"], path.stem)
                rand = np.sort(rng.integers(
                    lo, max(len(dfb) - C.E_TIME_STOP_H - 1, lo + 1),
                    len(ons) * 2))
                run(rand, dfb, C.E_TP_LADDER, None, C.E_TIME_STOP_H,
                    buckets["E_control"], path.stem)

    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in names:
        trades = buckets[name]
        if not trades:
            continue
        t = pd.DataFrame(trades)
        pnl = t["pnl"]
        w, l = pnl[pnl > 0], pnl[pnl <= 0]
        pf = float(w.sum() / -l.sum()) if l.sum() < 0 else float("inf")
        rows.append({"strategy": name, "n": len(t),
                     "EV/trade": f"{pnl.mean():+.2%}",
                     "win%": f"{(pnl > 0).mean():.0%}",
                     "PF": round(pf, 2)})
        t["period"] = (t["time"].dt.year.astype(str) + "-H"
                       + np.where(t["time"].dt.month <= 6, "1", "2"))
        buckets[name] = t

    print("\n=== EU UNIVERSE BACKTEST (signals: Binance / "
          "execution: OKX USDC) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n=== EV BY PERIOD ===")
    for name in names:
        t = buckets[name]
        if isinstance(t, pd.DataFrame) and len(t):
            print(f"\n{name}:")
            print(t.groupby("period")["pnl"].agg(n="count", ev="mean")
                  .round(4).to_string())

    big = pd.concat([t.assign(strategy=k) for k, t in buckets.items()
                     if isinstance(t, pd.DataFrame) and len(t)])
    big.to_csv(C.OUT_DIR / "eu_backtest.csv", index=False)
    print(f"\nSaved to {C.OUT_DIR / 'eu_backtest.csv'}")
    print(f"Costs assumed: {C.COST_ROUNDTRIP:.1%} round-trip (Kraken Pro "
          "base maker tier).\nAdopt per strategy ONLY if live beats its "
          "control in (nearly) every half-year.\nCaveat: EV computed on "
          "Binance USDT prices; Kraken USD/EUR fills track via arb\nbut "
          "thinner books cost extra spread - size small. "
          "Not financial advice.")


if __name__ == "__main__":
    main()
