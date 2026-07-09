"""Survey: which EU-accessible exchange can actually execute the strategies?

Checks the top-500 coin universe against 5 exchanges' public APIs and
reports, per exchange: how many coins are listed (EUR/USD/USDC quotes),
and their REAL 24h turnover distribution. Then, per coin, the best venue.

Exchanges: Binance (USDC), Coinbase, Kraken, OKX (USDC/EUR), Bitvavo (EUR),
Bybit (USDC/EUR), Gate.io (USDC/EUR).

    python exchange_survey.py       (~2-3 min; Coinbase is per-pair)
"""
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))

import config as C                    # noqa: E402  (europe)
from fetch_data import top_coins, get, session   # noqa: E402

THRESHOLDS = [1e6, 250e3, 50e3]


def survey_binance(symbols):
    """Binance USDC-quoted pairs (the EEA-compliant quote)."""
    info = get(f"{C.BINANCE_BASE}/api/v3/exchangeInfo")
    pairs = {s["baseAsset"].upper(): s["symbol"] for s in info["symbols"]
             if s["quoteAsset"] == "USDC" and s["status"] == "TRADING"}
    tick = get(f"{C.BINANCE_BASE}/api/v3/ticker/24hr")
    qvol = {t["symbol"]: float(t.get("quoteVolume") or 0) for t in tick}
    return {b: (p, qvol.get(p, 0.0)) for b, p in pairs.items()
            if b in symbols}


def survey_okx(symbols):
    data = get(f"{C.OKX_BASE}/api/v5/public/instruments",
               {"instType": "SPOT"}).get("data", [])
    pairs = {s["baseCcy"].upper(): s["instId"] for s in data
             if s["quoteCcy"] in ("USDC", "EUR") and s["state"] == "live"}
    tick = get(f"{C.OKX_BASE}/api/v5/market/tickers",
               {"instType": "SPOT"}).get("data", [])
    vol = {}
    for t in tick:
        try:
            last = float(t.get("last") or 0)
            vol[t["instId"]] = max(float(t.get("volCcy24h") or 0),
                                   float(t.get("vol24h") or 0) * last)
        except (TypeError, ValueError):
            pass
    return {b: (p, vol.get(p, 0.0)) for b, p in pairs.items()
            if b in symbols}


def survey_kraken(symbols):
    ap = get("https://api.kraken.com/0/public/AssetPairs").get("result", {})
    kmap = {}   # kraken pair key -> (base, wsname)
    alias = {"XBT": "BTC", "XDG": "DOGE"}
    for key, v in ap.items():
        ws = v.get("wsname", "")
        if "/" not in ws:
            continue
        base, quote = ws.split("/")
        base = alias.get(base, base).upper()
        if quote in ("USD", "EUR", "USDC") and base in symbols:
            if base not in kmap or quote == "USD":   # prefer USD book
                kmap[base] = (key, ws)
    out = {}
    keys = [k for k, _ in kmap.values()]
    for i in range(0, len(keys), 100):
        chunk = ",".join(keys[i:i + 100])
        res = get("https://api.kraken.com/0/public/Ticker",
                  {"pair": chunk}).get("result", {})
        for base, (key, ws) in kmap.items():
            t = res.get(key)
            if t:
                try:
                    v = float(t["v"][1]) * float(t["p"][1])  # 24h vol x vwap
                    out[base] = (ws, v)
                except (TypeError, ValueError, KeyError):
                    pass
        time.sleep(1)
    return out


def survey_coinbase(symbols):
    prods = get("https://api.exchange.coinbase.com/products")
    cand = {}
    for p in prods:
        if (p.get("quote_currency") in ("USD", "USDC", "EUR")
                and p.get("status") == "online"
                and not p.get("trading_disabled")):
            base = p["base_currency"].upper()
            if base in symbols and (base not in cand
                                    or p["quote_currency"] == "USD"):
                cand[base] = p["id"]
    out = {}
    for k, (base, pid) in enumerate(cand.items(), 1):
        if k % 50 == 0:
            print(f"    coinbase {k}/{len(cand)}")
        try:
            t = get(f"https://api.exchange.coinbase.com/products/{pid}/ticker")
            out[base] = (pid, float(t.get("volume") or 0)
                         * float(t.get("price") or 0))
        except Exception:
            pass
        time.sleep(0.15)
    return out


def survey_bybit(symbols):
    """Bybit spot, USDC/EUR quotes (EEA-compliant set)."""
    info = get("https://api.bybit.com/v5/market/instruments-info",
               {"category": "spot"})["result"]["list"]
    pairs = {}
    for s in info:
        if (s.get("quoteCoin") in ("USDC", "EUR")
                and s.get("status") == "Trading"):
            base = s["baseCoin"].upper()
            if base in symbols and (base not in pairs
                                    or s["quoteCoin"] == "USDC"):
                pairs[base] = s["symbol"]
    tick = get("https://api.bybit.com/v5/market/tickers",
               {"category": "spot"})["result"]["list"]
    vol = {t["symbol"]: float(t.get("turnover24h") or 0) for t in tick}
    return {b: (p, vol.get(p, 0.0)) for b, p in pairs.items()}


def survey_gate(symbols):
    """Gate.io spot, USDC/EUR quotes."""
    tick = get("https://api.gateio.ws/api/v4/spot/tickers")
    out = {}
    for t in tick:
        cp = t.get("currency_pair", "")
        if "_" not in cp:
            continue
        base, quote = cp.split("_", 1)
        base = base.upper()
        if quote in ("USDC", "EUR") and base in symbols:
            try:
                v = float(t.get("quote_volume") or 0)
            except (TypeError, ValueError):
                continue
            if base not in out or v > out[base][1]:
                out[base] = (cp, v)
    return out


def survey_bitvavo(symbols):
    tick = get("https://api.bitvavo.com/v2/ticker/24h")
    out = {}
    for t in tick:
        m = t.get("market", "")
        if not m.endswith("-EUR"):
            continue
        base = m.split("-")[0].upper()
        if base in symbols:
            try:
                out[base] = (m, float(t.get("volumeQuote") or 0))
            except (TypeError, ValueError):
                pass
    return out


def main():
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    coins = top_coins()
    symbols = {c["symbol"] for c in coins}
    ranks = {c["symbol"]: c["rank"] for c in coins}
    print(f"Universe: top {len(coins)} coins. Surveying 5 exchanges...\n")

    surveys = {}
    for name, fn in [("binance_usdc", survey_binance),
                     ("okx_usdc_eur", survey_okx),
                     ("kraken_usd_eur", survey_kraken),
                     ("coinbase_usd", survey_coinbase),
                     ("bitvavo_eur", survey_bitvavo),
                     ("bybit_usdc_eur", survey_bybit),
                     ("gate_usdc_eur", survey_gate)]:
        print(f"  querying {name}...")
        try:
            surveys[name] = fn(symbols)
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
            surveys[name] = {}

    print("\n=== EXCHANGE COVERAGE (of your top-500 universe) ===")
    rows = []
    for name, s in surveys.items():
        vols = sorted((v for _, v in s.values()), reverse=True)
        rows.append({
            "exchange": name, "coins_listed": len(s),
            ">=$1M/24h": sum(1 for v in vols if v >= 1e6),
            ">=$250k": sum(1 for v in vols if v >= 250e3),
            ">=$50k": sum(1 for v in vols if v >= 50e3),
            "median_24h": f"${vols[len(vols)//2]:,.0f}" if vols else "-",
        })
    print(pd.DataFrame(rows).to_string(index=False))

    # per-coin best venue
    recs = []
    for sym in symbols:
        best = None
        for name, s in surveys.items():
            if sym in s and (best is None or s[sym][1] > best[2]):
                best = (name, s[sym][0], s[sym][1])
        if best and best[2] >= 50e3:
            recs.append({"coin": sym, "rank": ranks.get(sym, 0),
                         "best_venue": best[0], "pair": best[1],
                         "usd_24h": round(best[2])})
    per = pd.DataFrame(recs).sort_values("rank")
    per.to_csv(C.OUT_DIR / "exchange_survey.csv", index=False)
    print(f"\nTradeable somewhere (>=$50k/24h): {len(per)} coins")
    print("Best venue counts:")
    print(per["best_venue"].value_counts().to_string())
    print(f"\nPer-coin table saved to {C.OUT_DIR / 'exchange_survey.csv'}")
    print("\nNote: coverage/liquidity only - check each venue's fee tier "
          "and your local\navailability. EUR turnover treated as ~USD. "
          "Not financial advice.")


if __name__ == "__main__":
    main()
