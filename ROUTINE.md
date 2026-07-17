# Operating Routine — trend_analyzer

The whole system on one page: what runs when, and what each output
obligates you to do. If an action isn't listed here, the answer is
"nothing" — the system's default state is *no trade*.

---

## DAILY (~10–15 min, ideally ~12:00 UTC)

```
python fetch_data.py                      # 1. refresh candles (~2-3 min)
python europe\screener_eu.py              # 2. the live board
python strategy_f\bid_helper.py           # 3. today's bid sheet
```

Optional context (not decision inputs): `breakout\screener_b.py`,
`e_combo\screener_e.py`, `whales\screener_w.py` on the wider universe.

### Decision table — screener_eu output

| Output | Trigger | Action |
|---|---|---|
| **B section** | fresh breakout, still ABOVE old high, decent `krk_24h` | **LIVE TRADE**: Kraken maker buy, stake = min(€1k, ~1–2% of hourly vol), set −25% stop, calendar exit day 7. Log. |
| B section | broke out but now below the old high | Skip — failed breakout, not the backtested trade |
| **W section** | fresh crossing (≤24h), absorb ≥80 | **PAPER ONLY**: log entry + BTC regime; check price again at day 7 and complete the row |
| **E section** | `z4 TRADE` + `silent=True` | Log as observation — E is not executable on your venues; it exists to watch and to test confluence patterns |
| E section | z2/z3 watch rows | Read, never act. Watch for coins climbing toward z4 |
| **BTC banner** | BELOW 100d MA | W paper entries get the regime flag; expect few B signals; F cascades more likely |
| Anything | dozens of simultaneous signals + stablecoin news | Stand aside — that's the quote moving, not the market |

### Decision table — bid sheet (strategy F pilot)

| Trigger | Action |
|---|---|
| New day | Cancel unfilled bids, place today's at `BID_at` (€100–200 each; skip new bids if 3 positions open) |
| **A bid FILLS** | Immediately place TP limit (+8%) and stop (−25%). Note the 48h time-stop deadline |
| Position open 48h | Close at market, log |
| Any fill/exit | Row in `strategy_f\fill_log.csv` — this log IS the pilot |

---

## EVENT-DRIVEN (whenever they occur)

| Event | Action |
|---|---|
| B position reaches day 7 | Sell at market, whatever the price. No extensions, ever |
| B stop (−25%) fires | Log it. Fires >1 in ~10 trades → flag for monthly review |
| W paper trade reaches day 7 | Complete the paper row (exit price, PnL) |
| F TP/stop/time-stop | Service the order, log |

---

## WEEKLY (~5 min)

```
python europe\fetch_data_eu.py            # refresh EU universe + Kraken liquidity
```

- Coins enter/leave the $250k bar — the screeners adapt automatically.
- Glance over both logs: anything unlogged? Fix while memory is fresh.
- Git hygiene: commit/push on the machine you worked on, pull on the other.

---

## MONTHLY (~30–45 min) — the kill-switch review

```
python analyze.py                          # parent stats refresh
python validate_edge.py                    # signal health (PASS/WARN/FAIL)
python europe\backtest_strategies.py       # E/W/B on EU universe at 0.5%
python experiments\backtest_breakout.py    # B deep-dive (its edge is decaying)
```

| Finding | Action |
|---|---|
| B's recent-period excess ≈ 0 or negative | **B stops trading.** No debate — this was pre-agreed |
| validate_edge = FAIL | Underlying volume signal decayed — freeze everything, investigate |
| Your live B log after 30+ trades: EV far below ~+3% | Signal fine, execution leaking — check fills/spreads before continuing |
| W paper log: performing like backtest across ≥30 entries incl. below-MA ones | Candidate for promotion to small live stakes — re-run the numbers first |
| W paper log: below-MA entries failing as history predicted | The regime rule graduates from banner to hard filter |

---

## QUARTERLY

- **F pilot verdict** (after 3 months): compare fills + EV vs the
  pre-registered criteria in `strategy_f\README.md`. Promote / archive —
  the criteria were written in advance precisely so this is mechanical.
- Re-read this file; update only through the same validation discipline
  that built it. Frozen configs stay frozen.

---

## STANDING RULES (no schedule — always)

1. No leverage. No exceptions — the no-stop strategies depend on it.
2. Maker orders only; never chase a moved price with a market buy.
3. Equal stakes within each strategy; sizing changes are a monthly
   decision, never an in-the-moment one.
4. Every discretionary override of a rule invalidates your own backtest —
   if a rule seems wrong, change it through a validated test, then follow
   the new rule.
5. The log is the product. An untracked trade teaches nothing.

Not financial advice.
