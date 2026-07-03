"""Download 6 months of 1h candles for the top-200 coins (Binance USDT pairs).

Resumable: already-downloaded symbols are skipped. Run:
    python fetch_data.py
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

import config as C

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]
NUM_COLS = ["open", "high", "low", "close", "volume",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"]

session = requests.Session()
session.headers["User-Agent"] = "trend-analyzer/1.0"


def get(url, params=None, retries=5):
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code == 418:
                wait = int(r.headers.get("Retry-After", 30))
                print(f"  rate limited, sleeping {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def top_coins():
    """Top-N coins by market cap from CoinGecko (symbol, name, market_cap)."""
    coins = []
    for page in (1, 2):
        coins += get(f"{C.COINGECKO_BASE}/coins/markets", {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": 100, "page": page, "sparkline": "false",
        })
        time.sleep(2)  # CoinGecko free tier is touchy
    out = []
    for c in coins[:C.TOP_N_COINS]:
        sym = c["symbol"].upper()
        if sym in C.EXCLUDE_SYMBOLS:
            continue
        out.append({"symbol": sym, "name": c["name"],
                    "market_cap": c.get("market_cap") or 0,
                    "rank": c.get("market_cap_rank") or 0})
    return out


def binance_usdt_symbols():
    """Set of base assets with an actively trading USDT pair on Binance."""
    info = get(f"{C.BINANCE_BASE}/api/v3/exchangeInfo")
    return {s["baseAsset"].upper(): s["symbol"]
            for s in info["symbols"]
            if s["quoteAsset"] == C.QUOTE_ASSET and s["status"] == "TRADING"}


def fetch_klines(pair, start_ms, end_ms):
    rows = []
    cur = start_ms
    while cur < end_ms:
        batch = get(f"{C.BINANCE_BASE}/api/v3/klines", {
            "symbol": pair, "interval": C.INTERVAL,
            "startTime": cur, "endTime": end_ms, "limit": C.KLINE_LIMIT,
        })
        if not batch:
            break
        rows += batch
        cur = batch[-1][6] + 1  # next after last close_time
        time.sleep(C.REQUEST_SLEEP)
        if len(batch) < C.KLINE_LIMIT:
            break
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=KLINE_COLS).drop(columns=["ignore"])
    for col in NUM_COLS:
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df.drop_duplicates("open_time").sort_values("open_time")


def main():
    C.KLINES_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching top coin list from CoinGecko...")
    coins = top_coins()
    print(f"  {len(coins)} coins after excluding stablecoins/wrapped assets")

    print("Fetching Binance USDT pairs...")
    pairs = binance_usdt_symbols()

    universe = [dict(c, pair=pairs[c["symbol"]]) for c in coins
                if c["symbol"] in pairs]
    skipped = [c["symbol"] for c in coins if c["symbol"] not in pairs]
    print(f"  {len(universe)} coins tradeable on Binance; "
          f"skipped {len(skipped)}: {', '.join(skipped[:20])}"
          + ("..." if len(skipped) > 20 else ""))

    with open(C.DATA_DIR / "universe.json", "w") as f:
        json.dump(universe, f, indent=1)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=C.LOOKBACK_DAYS)
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    for i, c in enumerate(universe, 1):
        path = C.KLINES_DIR / f"{c['pair']}.parquet"
        if path.exists():
            continue
        print(f"[{i}/{len(universe)}] {c['pair']}")
        try:
            df = fetch_klines(c["pair"], start_ms, end_ms)
        except Exception as e:
            print(f"  FAILED: {e}")
            continue
        if df is None or len(df) < 24 * 30:   # need at least ~1 month
            print("  insufficient history, skipping")
            continue
        df.to_parquet(path, index=False)

    n = len(list(C.KLINES_DIR.glob("*.parquet")))
    print(f"\nDone. {n} symbols cached in {C.KLINES_DIR}")
    if n == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
