"""Live whale-print inspector: individual large trades + TWAP/iceberg
detection from Binance aggTrades (public, no key).

    python whale_trades.py BTCUSDT           one pair
    python whale_trades.py                   top-5 from accumulation_now.csv

Shows:
  - every print >= BIG_TRADE_USD in the last SCAN_HOURS, with direction
  - net whale flow (aggressive buys minus sells among large prints)
  - TWAP/iceberg candidates: >= N near-identical clip sizes repeating
    (execution algos slice big orders into equal children - humans don't
    trade 847 identical clips)
"""
import sys
import time
from collections import defaultdict

import pandas as pd

import wconfig as W
from fetch_data import get, session   # parent module (truststore, retries)

import config as C                    # parent config for BINANCE_BASE


def fetch_agg_trades(pair, start_ms, end_ms):
    """All aggTrades in the window (paginated by fromId)."""
    out = []
    batch = get(f"{C.BINANCE_BASE}/api/v3/aggTrades",
                {"symbol": pair, "startTime": start_ms,
                 "endTime": min(start_ms + 3600_000, end_ms), "limit": 1000})
    while batch:
        out += batch
        last_id, last_t = batch[-1]["a"], batch[-1]["T"]
        if last_t >= end_ms:
            break
        batch = get(f"{C.BINANCE_BASE}/api/v3/aggTrades",
                    {"symbol": pair, "fromId": last_id + 1, "limit": 1000})
        time.sleep(0.1)
        if not batch or batch[-1]["T"] > end_ms + 3600_000:
            out += batch or []
            break
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df = df[(df["T"] >= start_ms) & (df["T"] <= end_ms)].copy()
    df["price"] = df["p"].astype(float)
    df["qty"] = df["q"].astype(float)
    df["usd"] = df["price"] * df["qty"]
    df["side"] = df["m"].map({True: "SELL", False: "BUY"})  # taker side
    df["time"] = pd.to_datetime(df["T"], unit="ms", utc=True)
    return df[["time", "price", "qty", "usd", "side"]]


def find_twap(df):
    """Groups of >= TWAP_MIN_REPEATS near-identical clip sizes."""
    groups = defaultdict(list)
    for _, r in df.iterrows():
        groups[round(r["qty"], 6)].append(r)
    # merge buckets within tolerance
    sizes = sorted(groups)
    merged, cur = [], [sizes[0]] if sizes else []
    for s in sizes[1:]:
        if cur and s <= cur[-1] * (1 + W.TWAP_SIZE_TOL):
            cur.append(s)
        else:
            merged.append(cur)
            cur = [s]
    if cur:
        merged.append(cur)
    out = []
    for bucket in merged:
        rows = [r for s in bucket for r in groups[s]]
        if len(rows) < W.TWAP_MIN_REPEATS:
            continue
        rr = pd.DataFrame(rows)
        usd = rr["usd"].sum()
        clip_usd = float(rr["usd"].median())
        # noise filters: retail-favorite sizes produce thousands of tiny
        # "identical" clips in mixed directions - real execution algos are
        # (a) meaningfully sized per clip, (b) directional
        if clip_usd < 500 or usd < W.BIG_TRADE_USD:
            continue
        buy_share = (rr["side"] == "BUY").mean()
        if 0.3 <= buy_share <= 0.7:
            continue                    # mixed = market-maker churn, skip
        span_min = (rr["time"].max() - rr["time"].min()).total_seconds() / 60
        out.append({"clip_size": round(rr["qty"].median(), 6),
                    "clip_usd": f"{clip_usd:,.0f}",
                    "n_clips": len(rr), "total_usd": f"{usd:,.0f}",
                    "span_min": round(span_min),
                    "direction": "BUY" if buy_share > 0.7 else "SELL"})
    return pd.DataFrame(out)


def scan(pair):
    now = int(time.time() * 1000)
    start = now - W.SCAN_HOURS * 3600_000
    print(f"\n##### {pair}: aggTrades, last {W.SCAN_HOURS}h #####")
    df = fetch_agg_trades(pair, start, now)
    if df.empty:
        print("no trades returned")
        return
    big = df[df["usd"] >= W.BIG_TRADE_USD]
    print(f"{len(df):,} trades total; {len(big)} prints >= "
          f"${W.BIG_TRADE_USD:,}")
    if len(big):
        net = (big.loc[big['side'] == 'BUY', 'usd'].sum()
               - big.loc[big['side'] == 'SELL', 'usd'].sum())
        print(f"net whale flow (large prints): {net:+,.0f} USD")
        show = big.nlargest(10, "usd").copy()
        show["usd"] = show["usd"].map("{:,.0f}".format)
        print(show.to_string(index=False))
    tw = find_twap(df)
    if len(tw):
        print("\nTWAP/iceberg candidates (directional, repeated equal clips):")
        print(tw.sort_values("n_clips", ascending=False)
              .head(8).to_string(index=False))
    else:
        print("no directional TWAP-like patterns found")


def main():
    if len(sys.argv) > 1:
        pairs = [a.upper() for a in sys.argv[1:]]
    else:
        try:
            acc = pd.read_csv(W.OUT_DIR / "accumulation_now.csv")
            pairs = acc["pair"].head(5).tolist()
            print("No pair given - inspecting top-5 accumulation candidates:",
                  ", ".join(pairs))
        except FileNotFoundError:
            sys.exit("Usage: python whale_trades.py <PAIR> "
                     "(or run accumulation.py first)")
    for p in pairs:
        try:
            scan(p)
        except Exception as e:
            print(f"{p}: FAILED - {e}")


if __name__ == "__main__":
    main()
