# Strategy F — Wick Catcher (calibration pilot)

Resting maker bids far below market, harvesting stop-cascade overshoots.
The passive twin of strategy W: instead of detecting the whale absorbing
panic, you *are* a (very small) absorber.

## Status: PILOT — measuring, not earning

The backtest (`../experiments/wick_catcher.py`, EU run) says C-depth
(−12% bids, +8% TP) made **+5.74%/trade, 92% win, positive in 6/6
half-years at 0.5% costs**, with controls at ~zero. But this strategy has
a flaw no backtest or paper trade can resolve: **phantom fills.** The
recorded hourly low is often a few dust trades in a microsecond air
pocket; a backtest fills your whole bid there, reality may fill nothing.
The deeper the wick, the worse the bias (the suspiciously perfect
E_20pct numbers are the tell). Survivorship bias (dead coins missing
from the universe) additionally flatters any crash-buying backtest.

**Only tiny real orders can measure your actual fill rate.** That is the
sole purpose of this pilot.

## Pilot rules (frozen — see fconfig.py)

- 10 most liquid Kraken coins, bids **12% below** the last close,
  re-priced once daily (backtest re-priced hourly; a known, accepted
  deviation for a manual pilot)
- On fill: TP limit **+8%**, disaster stop **−25%**, time-stop **48h**
- **€100–200 per bid**, max **3 open positions** (cascade days fill
  several bids at once — the cap is the risk control)
- Duration: **3 months**, every fill logged in `fill_log.csv`

## Success criteria (write down BEFORE the pilot ends)

Backtest prediction for this subset: roughly **8–15 fills over 3 months**
across 10 coins, EV ≈ +3–6% per fill (post-haircut expectation: half that).

- Fill rate ≥ half of predicted AND realized EV clearly positive →
  promote F to a small real strategy (still modest stakes; capacity is
  limited by how rarely deep wicks occur)
- Fills happen but EV ≈ 0 or negative → the snap-back doesn't survive
  real fills; archive with the data
- Almost no fills → phantom-fill bias confirmed; archive, and treat it
  as a cheap, valuable calibration of every deep-wick backtest you ever see

## Daily routine (folds into the usual one, ~5 min)

```
python ..\fetch_data.py     # if not already done today
python bid_helper.py        # prints today's order sheet
```

Then on Kraken: cancel stale bids, place today's, service any fills per
the sheet, log.

Not financial advice.
