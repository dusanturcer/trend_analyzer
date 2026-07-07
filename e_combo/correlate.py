"""Which indicators correlate with E-combo trade outcomes?

Reads output/e_trades.csv (from backtest_e.py) and, for every indicator:
  - Spearman correlation with trade PnL
  - Mann-Whitney test: winners vs losers distributions
  - EV in bottom / middle / top tercile of the indicator

    python correlate.py

IMPORTANT: with ~14 indicators and ~90 trades this is HYPOTHESIS GENERATION,
not proof. Expect ~1 indicator to look significant at p<0.05 by pure chance.
Only p<0.01 with a sensible economic story deserves a follow-up - and any
filter built from this MUST be re-validated on future data before use.
"""
import numpy as np
import pandas as pd
from scipy import stats

import econfig as E
from indicators import INDICATOR_COLS

CANDIDATES = INDICATOR_COLS + ["btc_ret_24h", "vol_z"]


def tercile_ev(t, col):
    try:
        bins = pd.qcut(t[col], 3, labels=["low", "mid", "high"],
                       duplicates="drop")
    except ValueError:
        return None
    return t.groupby(bins, observed=True)["pnl"].mean()


def main():
    t = pd.read_csv(E.OUT_DIR / "e_trades.csv")
    print(f"{len(t)} trades, overall EV {t['pnl'].mean():+.2%}\n")

    rows = []
    for col in CANDIDATES:
        if col not in t:
            continue
        s = t[[col, "pnl", "win"]].dropna()
        if len(s) < 30 or s[col].nunique() < 5:
            continue
        rho, p_rho = stats.spearmanr(s[col], s["pnl"])
        wn, ls = s.loc[s["win"], col], s.loc[~s["win"], col]
        p_mw = (stats.mannwhitneyu(wn, ls).pvalue
                if len(wn) > 4 and len(ls) > 4 else np.nan)
        te = tercile_ev(s, col)
        rows.append({
            "indicator": col, "n": len(s),
            "spearman": round(float(rho), 3),
            "p": f"{p_rho:.3f}",
            "p_MW": f"{p_mw:.3f}" if p_mw == p_mw else "n/a",
            "EV_low": f"{te.get('low', np.nan):+.2%}" if te is not None else "",
            "EV_mid": f"{te.get('mid', np.nan):+.2%}" if te is not None else "",
            "EV_high": f"{te.get('high', np.nan):+.2%}" if te is not None else "",
        })

    out = pd.DataFrame(rows).sort_values("p")
    print(out.to_string(index=False))

    sig = out[out["p"].astype(float) < 0.01]
    print(f"\n{len(sig)} indicator(s) at p<0.01 "
          f"(chance expectation with {len(out)} tests: ~{len(out) * 0.01:.1f})")
    if len(sig):
        print("Candidates worth a follow-up:", ", ".join(sig["indicator"]))
    print("\nReminder: this explores ONE dataset. Any filter derived here "
          "must prove itself on NEW data (validate_edge.py / paper trading) "
          "before real use.")
    out.to_csv(E.OUT_DIR / "indicator_correlations.csv", index=False)


if __name__ == "__main__":
    main()
