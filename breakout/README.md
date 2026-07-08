# Strategy B — 30d-High Breakout

The third validated strategy, born from the indicator playbook study:
a fresh break above the prior 30-day high is the strongest bullish context
in 3 years of data — and the only strategy that stayed positive in the
2025-H1 regime that hurt E and W.

## Live rules (frozen — changing them = new strategy, re-validate)

1. Enter on a fresh 30d-high breakout (first cross, 48h dedup per coin),
   liquid pairs only (≥ $100k/h median).
2. Set a **−25% disaster stop** immediately (tail insurance: ~0.30%/trade).
3. **No take-profit.** Sell after 7 days, whatever the price.
4. Equal stakes. ~7 positions open on average at full signal flow.

## Evidence (experiments/backtest_breakout.py, 3 years, 1123 trades)

| | EV/trade | win% | PF | worst |
|---|---|---|---|---|
| hold 7d, no stop | +3.65% | 49% | 1.78 | −35% |
| **live rules (−25% stop)** | **+3.35%** | 49% | 1.68 | −25% |
| TP ladder +8/+15 | +1.50% | 60% | 1.40 | — |
| random control | +0.91% | 46% | 1.20 | — |

Beat the control in **6 of 6 half-years**, including +1.1% absolute in
2025-H1. The TP-ladder row is why there's no take-profit: breakouts trend,
and capping winners halves the edge. Expect half the trades to fail —
the edge is the asymmetry of the wins, not their frequency.

**Caveat:** excess over control shrank from ~+3% (2023–24) to ~+0.9%
(2025–26). Still positive everywhere, but re-validate monthly by re-running
`../experiments/backtest_breakout.py` after a data refresh.

## Daily routine

```
python ../fetch_data.py      # incremental
python screener_b.py         # regime banner + fresh breakouts
```

## Portfolio context

Three complementary strategies on one data stack:

| | logic | hold | trades/yr | regime weakness |
|---|---|---|---|---|
| E-combo | silent volume spike (quiet before storm) | ≤36h | ~50 | mild in 2025-H1 |
| W | absorbed selling (buy hidden strength) | 7d | ~300 | failed 2025-H1 |
| B | 30d-high breakout (buy confirmed strength) | 7d | ~375 | none observed, edge narrowing |

Combined capital at full flow: ~13–15 stakes. Not financial advice.
