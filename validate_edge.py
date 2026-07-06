"""Is the edge still there? Run after `fetch_data.py` + `analyze.py`.

Compares the screener profile's recent hit rate (last VALIDATE_RECENT_DAYS)
against its long-term baseline and the market base rate, and prints a
PASS / WARN / FAIL verdict.

    python validate_edge.py
"""
import sys

import pandas as pd
from scipy import stats

import config as C

VALIDATE_RECENT_DAYS = 90     # "recent" window to test
MIN_RECENT_SIGNALS = 30       # below this, no statistical verdict possible
MIN_LIFT = 1.5                # recent lift below this = edge considered gone
PROFILE_TIERS = {"mid", "small", "micro", "tiny"}
PROFILE_MIN_Z = 3.0           # must match what you act on (screener profile)


def main():
    sig = pd.read_csv(C.OUT_DIR / "signals.csv")
    if "time" not in sig.columns:
        sys.exit("signals.csv has no 'time' column - re-run analyze.py first")
    sig["time"] = pd.to_datetime(sig["time"], utc=True, format="mixed")

    # drop signals whose forward window couldn't complete (edge of data)
    data_end = sig["time"].max()
    sig = sig[sig["time"] <= data_end - pd.Timedelta(hours=C.PUMP_WINDOW_H)]

    prof = sig[(sig["vol_z"] >= PROFILE_MIN_Z)
               & sig["tier"].isin(PROFILE_TIERS)]
    cut = data_end - pd.Timedelta(days=VALIDATE_RECENT_DAYS)
    recent, past = prof[prof["time"] > cut], prof[prof["time"] <= cut]

    # base rate: prefer the current period's, else overall
    try:
        br = pd.read_csv(C.OUT_DIR / "base_rates.csv")
        base = float(br["base_rate"].iloc[-1])
        base_overall = float(br["overall"].iloc[0])
    except FileNotFoundError:
        base = base_overall = float("nan")

    n_r, k_r = len(recent), int(recent["pumped"].sum())
    n_p, k_p = len(past), int(past["pumped"].sum())
    hit_r = k_r / n_r if n_r else float("nan")
    hit_p = k_p / n_p if n_p else float("nan")
    lift = hit_r / base if base == base and base > 0 else float("nan")

    print(f"Profile: silent spike z>={PROFILE_MIN_Z}, tiers "
          f"{sorted(PROFILE_TIERS)}, pump = >={C.PUMP_THRESHOLD:.0%} "
          f"in {C.PUMP_WINDOW_H}h")
    print(f"Data through: {data_end:%Y-%m-%d}")
    print(f"Baseline ({n_p} signals): hit {hit_p:.1%}")
    print(f"Recent {VALIDATE_RECENT_DAYS}d ({n_r} signals): hit {hit_r:.1%}"
          + (f", lift {lift:.1f}x vs base {base:.1%}" if lift == lift else ""))

    if n_r < MIN_RECENT_SIGNALS:
        print(f"\nVERDICT: WARN - only {n_r} recent signals "
              f"(need {MIN_RECENT_SIGNALS}); no reliable verdict. "
              "Widen VALIDATE_RECENT_DAYS or wait for more data.")
        return

    # is the recent hit rate statistically consistent with the baseline?
    p_worse = stats.binomtest(k_r, n_r, hit_p, alternative="less").pvalue

    if lift == lift and lift < MIN_LIFT:
        print(f"\nVERDICT: FAIL - recent lift {lift:.1f}x is below "
              f"{MIN_LIFT}x. The signal is barely beating a random hour. "
              "Stop acting on flags until this recovers.")
    elif p_worse < 0.05 and hit_r < hit_p:
        print(f"\nVERDICT: FAIL - recent hit rate is significantly below "
              f"baseline (p={p_worse:.3f}). The edge has likely decayed. "
              "Stop acting on flags; re-check next month.")
    elif hit_r < hit_p * 0.75:
        print(f"\nVERDICT: WARN - recent hit rate is {hit_r/hit_p:.0%} of "
              f"baseline (not yet statistically significant, "
              f"p={p_worse:.3f}). Reduce size; re-validate soon.")
    else:
        print(f"\nVERDICT: PASS - edge intact "
              f"(recent {hit_r:.1%} vs baseline {hit_p:.1%}, "
              f"p={p_worse:.3f}).")


if __name__ == "__main__":
    main()
