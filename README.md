# Crypto Pump Analyzer

Detects quick price jumps ("pumps") and drops in the top-200 coins over the last
6 months of hourly Binance data, then analyzes what preceded them — especially
volume anomalies — and compares against a random control group to measure real
predictive value.

## Quick start (run on your own machine)

```
pip install -r requirements.txt
python fetch_data.py          # ~10-20 min: downloads 6 months of 1h candles
python analyze.py             # detects events, extracts features, writes report
```

Then open `output/report.html`.

## What you get

| File | Contents |
|---|---|
| `output/report.html` | Full findings: precursor stats vs control group, conditional probabilities, clusters, breakdowns, charts |
| `output/events.csv` | Every detected pump/dump with all precursor features |
| `output/sweep.csv` | Event counts across all threshold/window definitions |
| `output/charts/` | Price+volume charts of notable events |
| `data/klines/*.parquet` | Cached raw candles (delete to force re-download) |

## Is the edge still there?

```
python validate_edge.py
```

Run monthly after refreshing data (`fetch_data.py` + `analyze.py`). Compares
the screener profile's last-90-days hit rate against its long-term baseline
and prints PASS / WARN / FAIL. FAIL = stop acting on flags.

## Optional: live screener

```
python screener.py
```

Scans current Binance data for coins showing the precursor signature right now
(volume spike without a big price move yet). Prints a ranked watchlist.

## Tuning

Edit `config.py` — pump threshold/window, sweep grid, precursor window,
volume-spike z-score, etc. Re-run `analyze.py` (no re-download needed).

## Notes

- Data: Binance public API first, OKX public API as fallback for coins not
  on Binance (no keys needed), + CoinGecko free API for the top-200 list.
  Only coins on neither exchange are skipped. Stablecoins/wrapped assets
  excluded. OKX candles lack taker-buy volume and trade counts, so the
  buy-ratio and trades-z features are blank (NaN) for OKX coins.
- `fetch_data.py` is resumable — re-run it if it's interrupted.
- This is statistical analysis of past data, not financial advice. Past
  patterns may not persist.

## Tests

```
python -m pytest test_pipeline.py -q
```

Runs the pipeline on synthetic data with planted pumps.
