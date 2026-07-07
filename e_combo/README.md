# E-combo

Focused workspace for the one variant that showed promise in the 18-month
variant test: **silent volume spikes z >= 4, mid-cap and below, liquid pairs,
no stop-loss, 36h time stop, TP ladder +8%/+15%, maker execution (0.2% RT).**

Historical stats (18 months, 93 trades): EV +1.11%/trade, win 59%, PF 1.42 —
but **negative in 2025-H1** and small sample. Status: paper-trade candidate,
not proven.

Uses the parent project's data (`../data`) — run the parent's
`fetch_data.py` first / to refresh.

## Scripts

| Script | What it does |
|---|---|
| `backtest_e.py` | Backtests E-combo only; saves every trade WITH ~15 indicators measured at entry (`output/e_trades.csv`) |
| `correlate.py` | Tests which indicators separate winning from losing trades (Spearman, Mann-Whitney, tercile EV) |
| `screener_e.py` | Live watchlist of current E-combo signals, indicators included |
| `econfig.py` | Frozen strategy parameters + indicator settings |
| `indicators.py` | RSI, Bollinger width percentile, 30d-high distance, OBV change, MACD, ATR percentile, VWAP distance, momentum, BTC context, time-of-day |

## Workflow

```
cd e_combo
python backtest_e.py     # ~2-5 min
python correlate.py      # indicator correlation table
python screener_e.py     # live candidates (rare: ~1-2/week)
```

## Ground rules

- ~90 trades and ~15 indicators = hypothesis generation. Expect one indicator
  to look "significant" by chance. Only p<0.01 + an economic story counts.
- Any filter you add based on `correlate.py` creates a NEW strategy that must
  be re-validated on future data before trading it.
- The parent's `validate_edge.py` remains the monthly kill switch.
- Not financial advice; historical patterns can stop working at any time.
