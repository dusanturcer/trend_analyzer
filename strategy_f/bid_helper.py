"""Daily bid sheet for the strategy-F pilot.

Reads the shared candle cache + EU universe, picks the N most liquid
Kraken coins, and prints today's order sheet: where to place each resting
bid, and the TP/stop levels to set if it fills.

    python ..\\fetch_data.py     # refresh candles first
    python bid_helper.py
"""
import json

import pandas as pd

import fconfig as F


def main():
    F.OUT_DIR.mkdir(exist_ok=True)
    with open(F.EU_UNIVERSE) as f:
        universe = json.load(f)
    universe.sort(key=lambda c: -c.get("venue_usd_24h", 0))
    picks = universe[:F.N_COINS]

    rows, stale = [], []
    now = pd.Timestamp.now(tz="UTC")
    for c in picks:
        p = F.KLINES_DIR / f"{c['pair']}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        last = float(df["close"].iloc[-1])
        age_h = (now - df["open_time"].iloc[-1]).total_seconds() / 3600
        if age_h > 26:
            stale.append(c["symbol"])
        bid = last * (1 - F.DEPTH)
        rows.append({
            "coin": c["symbol"],
            "kraken_pair": c.get("exec_pair", "?"),
            "last_close": round(last, 6),
            "BID_at": round(bid, 6),
            "if_filled_TP": round(bid * (1 + F.TP), 6),
            "if_filled_STOP": round(bid * (1 + F.DISASTER_STOP), 6),
            "krk_24h": f"{c.get('venue_usd_24h', 0)/1e6:,.1f}M",
        })

    print(f"=== STRATEGY F pilot - daily bid sheet "
          f"({now:%Y-%m-%d %H:%M} UTC) ===\n")
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    out.to_csv(F.OUT_DIR / "bid_sheet.csv", index=False)
    if stale:
        print(f"\nWARNING: stale candles for {', '.join(stale)} - "
              "run ..\\fetch_data.py first.")
    lo, hi = F.STAKE_EUR
    print(f"""
PROCEDURE (once per day, ~5 min):
 1. Cancel yesterday's unfilled bids, place today's at BID_at
    (limit buy, EUR {lo}-{hi} each, max {F.MAX_OPEN_POSITIONS} open
    positions - if at cap, place no new bids).
 2. On any fill: immediately place the TP limit sell and the stop.
    Time-stop: if still open after {F.TIME_STOP_H}h, close at market.
 3. Log EVERY fill in fill_log.csv (also log bids that were touched
    but did NOT fill, if you can see it - that's the phantom-fill data).
Calibration pilot: sized to measure fill reality, not to earn.
Not financial advice.""")


if __name__ == "__main__":
    main()
