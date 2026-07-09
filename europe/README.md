# Europe — Kraken execution variant

For trading from Europe on Kraken (USD/EUR pairs), keeping the validated
signal source.

## Venue decision (from `exchange_survey.py`, 7 exchanges surveyed)

| exchange | listed | ≥$1M/24h | ≥$250k | median |
|---|---|---|---|---|
| Coinbase USD | 176 | 42 | 88 | $249k |
| Binance USDC | 155 | 29 | 78 | $261k |
| **Kraken USD/EUR** | **241** | 22 | 61 | $59k |
| Bitvavo EUR | 200 | 14 | 47 | $55k |
| Bybit / OKX / Gate (USDC/EUR) | — | dead books | — | — |

Kraken chosen for account availability. Trade-off accepted: **fees.**
Kraken Pro base tier ≈ 0.25% maker per side → **0.5% round-trip**, 2.5x
the Binance assumption every backtest was validated at. All EU backtests
therefore run at 0.5% costs — strategies must re-earn their stakes.

## Architecture

- **Signals from Binance USDT candles** (validated source; taker data
  keeps strategy W alive). Candles shared with parent (`../data/klines`).
- **Execution on Kraken USD/EUR** (USD book preferred where both exist).
  Prices track across venues via arbitrage; spreads on thinner Kraken
  books are an extra, unmodeled cost — size small, always maker orders.
- Universe = top-500 ∩ Binance ∩ Kraken with ≥ $250k/24h Kraken turnover.

## Scripts

| Script | What it does |
|---|---|
| `exchange_survey.py` | The 7-exchange coverage/liquidity survey (rerun if venue doubts return) |
| `fetch_data_eu.py` | Builds the EU universe with Kraken pairs + turnover. Run weekly. |
| `backtest_strategies.py` | **Run before trading**: E, W, B + controls on this universe at 0.5% costs |
| `screener_eu.py` | Daily driver: BTC regime + fresh E/W/B signals with Kraken execution pairs |
| `run_analyze.py` / `run_validate.py` | Full parent analysis / edge validation on the EU universe |

## Routine

```
python fetch_data_eu.py       # weekly: refresh universe
python ..\fetch_data.py       # daily: refresh shared candles (incremental)
python screener_eu.py         # daily: signals
```

## Must-do before live use

Run `backtest_strategies.py`. Two headwinds vs the parent results, and the
backtest prices both: this universe drops non-Kraken coins (including many
small caps where E-combo was strongest), and costs are 0.5% instead of
0.2%. Rough expectations: E-combo is most at risk (+1.6% edge minus +0.3%
extra costs), B most likely to survive (+3.35%), W in between (+2.8%,
regime caveat unchanged). Each strategy must beat its control in (nearly)
every half-year **at these costs** to earn stakes. Kraken fee tiers drop
with volume — if your tier improves, update `COST_ROUNDTRIP` in config.py
and re-run.

Not financial advice.
