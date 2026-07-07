"""Download 6 months of 1h candles for the top-200 coins.

Binance USDT pairs are used first; coins not on Binance fall back to OKX
USDT spot pairs. Note: OKX candles have no taker-buy volume / trade count,
so those features are NaN for OKX coins.

Resumable: already-downloaded symbols are skipped. Run:
    python fetch_data.py
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

try:  # trust the Windows certificate store (needed behind corporate proxies)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

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
    n_pages = -(-C.TOP_N_COINS // 100)
    for page in range(1, n_pages + 1):
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


def okx_usdt_symbols():
    """Set of base assets with a live USDT spot pair on OKX."""
    data = get(f"{C.OKX_BASE}/api/v5/public/instruments",
               {"instType": "SPOT"}).get("data", [])
    return {s["baseCcy"].upper(): s["instId"] for s in data
            if s["quoteCcy"] == C.QUOTE_ASSET and s["state"] == "live"}


def fetch_okx_klines(inst_id, start_ms, end_ms):
    """1h candles from OKX (newest-first pages of 100, paginated backwards)."""
    raw = []
    after = str(end_ms)
    while True:
        resp = get(f"{C.OKX_BASE}/api/v5/market/history-candles", {
            "instId": inst_id, "bar": "1H", "limit": 100, "after": after})
        data = resp.get("data", [])
        if not data:
            break
        raw += data
        oldest = int(data[-1][0])
        if oldest <= start_ms:
            break
        after = str(oldest)
        time.sleep(C.REQUEST_SLEEP)
    rows = []
    for k in raw:
        ts = int(k[0])
        if ts < start_ms or ts > end_ms:
            continue
        o, h, lo, c_ = map(float, k[1:5])
        vol = float(k[5])
        quote = float(k[7]) if len(k) > 7 and k[7] else vol * c_
        rows.append({
            "open_time": ts, "open": o, "high": h, "low": lo, "close": c_,
            "volume": vol, "close_time": ts + 3600_000 - 1,
            "quote_volume": quote,
            "trades": np.nan,                 # not provided by OKX
            "taker_buy_base": np.nan, "taker_buy_quote": np.nan,
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df.drop_duplicates("open_time").sort_values("open_time")


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
    bnc = binance_usdt_symbols()
    print("Fetching OKX USDT pairs...")
    try:
        okx = okx_usdt_symbols()
    except requests.RequestException as e:
        print(f"  WARNING: OKX unreachable ({type(e).__name__}) - "
              "continuing with Binance coins only")
        okx = {}

    universe, skipped = [], []
    for c in coins:
        if c["symbol"] in bnc:
            universe.append(dict(c, pair=bnc[c["symbol"]], exchange="binance"))
        elif c["symbol"] in okx:
            universe.append(dict(c, pair=okx[c["symbol"]], exchange="okx"))
        else:
            skipped.append(c["symbol"])
    n_b = sum(1 for c in universe if c["exchange"] == "binance")
    print(f"  {n_b} coins on Binance, {len(universe) - n_b} more on OKX; "
          f"skipped {len(skipped)}: {', '.join(skipped[:20])}"
          + ("..." if len(skipped) > 20 else ""))

    with open(C.DATA_DIR / "universe.json", "w") as f:
        json.dump(universe, f, indent=1)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=C.LOOKBACK_DAYS)
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    for i, c in enumerate(universe, 1):
        path = C.KLINES_DIR / f"{c['pair']}.parquet"
        fetcher = (fetch_okx_klines if c["exchange"] == "okx"
                   else fetch_klines)

        if path.exists():
            try:
                old = pd.read_parquet(path)
                t0, t1 = old["open_time"].min(), old["open_time"].max()
                if t0 <= start + timedelta(days=7):
                    # window start covered -> incremental top-up only
                    gap_ms = int(t1.timestamp() * 1000)  # refetch last bar
                    if gap_ms >= end_ms - 3_600_000:
                        continue                          # already current
                    print(f"[{i}/{len(universe)}] {c['pair']} "
                          f"(update from {t1:%Y-%m-%d %H:%M})")
                    try:
                        new = fetcher(c["pair"], gap_ms, end_ms)
                    except Exception as e:
                        print(f"  FAILED: {e}")
                        continue
                    if new is not None and len(new):
                        df = (pd.concat([old[old["open_time"] < t1], new])
                              .drop_duplicates("open_time")
                              .sort_values("open_time"))
                        df.to_parquet(path, index=False)
                    continue
            except Exception:
                pass  # unreadable cache -> full re-download below

        print(f"[{i}/{len(universe)}] {c['pair']} ({c['exchange']}) full")
        try:
            df = fetcher(c["pair"], start_ms, end_ms)
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
