# Europe — OKX/USDC execution variant

For trading from Europe on OKX with USDC pairs, while keeping the
validated signal source.

## Architecture

**Signals from Binance candles, execution on OKX USDC.** Your own data
showed why: volume signals are only reliable from a coin's primary venue
(OKX-sourced signals hit 4.8% vs 8.5% for Binance-sourced), while prices
track across exchanges via arbitrage within seconds. So this variant:

- Universe = top-500 coins with **both** a Binance USDT pair (data) and a
  live OKX USDC pair with ≥ $1M/24h OKX turnover (execution)
- Candles = **shared** with the parent project (`../data/klines`) — no
  duplicate downloads; refresh with the parent `fetch_data.py`
- All three strategies available (Binance candles carry taker data, so W works)
- Every watchlist row shows the OKX pair to execute on + its 24h turnover

## Scripts

| Script | What it does |
|---|---|
| `fetch_data_eu.py` | Builds the EU universe (CoinGecko ∩ Binance ∩ OKX-USDC, liquidity-filtered). Run weekly. |
| `backtest_strategies.py` | **Run before trading**: E, W, B + random controls on this restricted universe |
| `screener_eu.py` | Daily driver: BTC regime banner + fresh E/W/B signals with OKX execution pairs |
| `run_analyze.py` / `run_validate.py` | Full parent analysis / edge validation on the EU universe |
| `config.py` | EU settings; mirrors the parent config interface |

## Routine

```
python fetch_data_eu.py       # weekly: refresh universe
python ..\fetch_data.py       # daily: refresh shared candles (incremental)
python screener_eu.py         # daily: signals
```

## Must-do before live use

Run `backtest_strategies.py`. The full-universe numbers do NOT
automatically transfer: this universe drops coins without OKX USDC
listings — disproportionately the small caps where E-combo's edge was
strongest. Each strategy must beat its control in (nearly) every
half-year **on this universe** to earn stakes.

## Known caveats

- Backtest EVs are computed on Binance USDT prices; OKX USDC fills track
  closely via arb, but USDC books are thinner — check the `okx_24h`
  column before sizing, prefer maker orders, size small.
- USDT/USDC is not exactly 1:1 (usually within a few bps) — negligible at
  these edge sizes, but it exists.
- W's regime weakness (BTC below 100d MA) applies unchanged.

Not financial advice.
