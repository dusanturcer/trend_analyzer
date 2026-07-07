"""Accumulation scoring: who is being quietly bought in batches?

Computes a 0-100 composite score per coin per hour from cached klines,
prints the current leaderboard, and saves scores for validation.

    python accumulation.py            (run from the whales folder)

Score components (each a percentile rank vs the coin's own last 90 days):
  flow    - net aggressive flow over 72h: sum(taker buys - taker sells)
  clip    - average trade size over 72h (quote volume / trade count)
  quiet   - LOW price volatility over 72h (batches sized not to move price)
  diverge - flow rank minus price-return rank (money in, price flat)

composite = (flow + clip + quiet) / 3, only valid while |72h return| < 8%.
"""
import json

import numpy as np
import pandas as pd

import wconfig as W

SCORE_COLS = ["flow", "clip", "quiet", "diverge", "score"]


def rank_pct(s: pd.Series) -> pd.Series:
    return s.rolling(W.RANK_WINDOW_H, min_periods=24 * 14).rank(pct=True) * 100


def add_accumulation(df: pd.DataFrame) -> pd.DataFrame:
    """df: raw hourly klines (Binance schema). Adds score columns."""
    df = df.reset_index(drop=True).copy()
    qv, tb = df["quote_volume"], df["taker_buy_quote"]
    c = df["close"]
    H = W.ACC_WINDOW_H

    net_flow = (2 * tb - qv).rolling(H).sum()          # buys minus sells, $
    df["flow"] = rank_pct(net_flow)

    clip = (qv / df["trades"].replace(0, np.nan)).rolling(H).mean()
    df["clip"] = rank_pct(clip)

    vol = c.pct_change().rolling(H).std()
    df["quiet"] = 100 - rank_pct(vol)

    ret_rank = rank_pct(c.pct_change(H))
    df["diverge"] = df["flow"] - ret_rank

    df["score"] = (df["flow"] + df["clip"] + df["quiet"]) / 3
    df.loc[c.pct_change(H).abs() >= W.QUIET_MAX_ABS_RET, "score"] = np.nan

    # --- v2: ABSORPTION score -------------------------------------------
    # Patient whales buy passively: heavy taker SELLING that fails to move
    # price down = someone big is soaking up the sells on the bid.
    sell_flow = rank_pct((qv - 2 * tb).rolling(H).sum())   # net taker sells
    ret_h = c.pct_change(H)
    resilience = 100 - rank_pct(-ret_h)   # high = price did NOT fall
    df["absorb"] = np.where(
        (sell_flow >= 50) & (ret_h > -0.03),
        (sell_flow + df["clip"] + resilience) / 3, np.nan)
    return df


def main():
    W.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(W.DATA_DIR / "universe.json") as f:
        universe = {c["pair"]: c for c in json.load(f)}

    rows = []
    files = sorted(W.KLINES_DIR.glob("*.parquet"))
    print(f"Scoring {len(files)} coins for whale accumulation...")
    for n, path in enumerate(files, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(files)}")
        meta = universe.get(path.stem)
        if meta is None or meta.get("exchange") == "okx":
            continue                       # OKX candles lack whale fields
        df = pd.read_parquet(path)
        if (df["quote_volume"].tail(24 * 30).median() < W.MIN_USD_PER_H
                or df["trades"].isna().all()):
            continue
        df = add_accumulation(df)
        last = df.iloc[-1]
        if not np.isfinite(last["score"]):
            continue
        ret72 = float(df["close"].iloc[-1] / df["close"].iloc[-W.ACC_WINDOW_H] - 1)
        rows.append({
            "coin": meta["symbol"], "pair": path.stem, "rank": meta["rank"],
            "score": round(float(last["score"]), 1),
            "absorb": (round(float(last["absorb"]), 1)
                       if np.isfinite(last["absorb"]) else None),
            "flow": round(float(last["flow"]), 0),
            "clip": round(float(last["clip"]), 0),
            "quiet": round(float(last["quiet"]), 0),
            "diverge": round(float(last["diverge"]), 0),
            "ret_72h": f"{ret72:+.1%}",
        })

    if not rows:
        print("No scoreable coins - is ../data populated?")
        return
    out = pd.DataFrame(rows).sort_values("score", ascending=False)
    hot = out[out["score"] >= W.SCORE_ALERT]
    print(f"\n=== Accumulation leaderboard "
          f"({len(hot)} above alert level {W.SCORE_ALERT}) ===\n")
    print(out.head(25).to_string(index=False))
    out.to_csv(W.OUT_DIR / "accumulation_now.csv", index=False)
    print(f"\nSaved to {W.OUT_DIR / 'accumulation_now.csv'}")
    print("High score = 3 days of unusual net buying, in unusually large "
          "clips, without moving price - the batch-accumulation signature.")
    print("Check what it's historically worth: python validate_whales.py")
    print("Inspect live whale prints on a candidate: "
          "python whale_trades.py <PAIR>")


if __name__ == "__main__":
    main()
