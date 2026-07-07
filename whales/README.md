# Whale Scanner

Detects whale behavior — including slow batch accumulation — from public
Binance data. Shares the parent project's data (`../data`); Binance coins
only (OKX candles lack taker-buy and trade-count fields).

## The idea

A whale buying $2M of a mid-cap can't market-buy it at once, so they slice
it into batches over days, sized to not move the price. That leaves four
fingerprints in public data:

1. **flow** — taker-buy share stays elevated for days (net aggressive buying)
2. **clip** — average trade size (volume/trade count) creeps up
3. **quiet** — price volatility is LOW while it happens (that's the point)
4. **diverge** — money flows in, price goes nowhere... yet

Plus, live: execution algos (TWAP/iceberg) print near-identical clip sizes
dozens of times — a machine signature humans don't produce.

## Scripts

| Script | What it does |
|---|---|
| `accumulation.py` | Scores every coin 0–100 on v1 accumulation + v2 absorption; prints today's leaderboard |
| `validate_whales.py` | The honesty check: bucketed forward returns, lift vs base rate, per-period robustness (v1 FAILED, v2 passed) |
| `backtest_w.py` | Trades the absorption signal with fixed rules + a random-entry market-beta control |
| `screener_w.py` | **Daily driver**: fresh absorb≥80 crossings + BTC 100d-MA regime banner |
| `whale_trades.py PAIR` | Live drill-down: individual prints ≥ $25k in the last 6h, net whale flow, TWAP/iceberg detection |
| `wconfig.py` | All thresholds |

## Validated strategy (W, backtest variant C)

Enter on a fresh absorb≥80 crossing, hold 7 days flat, sell. No stop, no TP.
18-month+ backtest (905 trades): **+3.1%/trade, +2.9% excess over random
entries, positive excess in 5 of 6 half-years.** Known weakness: when BTC
trades below its 100d MA (2025-H1), absorption entries underperformed even
random ones — the screener shows a regime banner for exactly this.
~6 positions open on average; budget ~6–8 stakes of capital.

## Daily routine

```
python ../fetch_data.py     # incremental, a few minutes
python screener_w.py        # regime banner + fresh crossings
```

## Workflow

```
cd whales
python accumulation.py       # leaderboard from cached data (refresh via parent fetch_data.py)
python validate_whales.py    # what a high score was historically worth
python whale_trades.py XYZUSDT   # inspect live whale prints on a candidate
```

## Ground rules

- Run `validate_whales.py` BEFORE trusting the leaderboard — if the 80+
  bucket doesn't beat the low buckets consistently across periods, the
  signature (in this form) is not tradeable, just interesting.
- This measures *exchange* flow. It cannot see OTC deals, cold-wallet moves,
  or whether the "whale" is one entity or a crowd. Treat as evidence, not truth.
- Not financial advice.
