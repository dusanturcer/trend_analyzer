"""Print the key findings as compact text. Run: python summary.py"""
import pandas as pd

ev = pd.read_csv("output/events.csv")
sig = pd.read_csv("output/signals.csv")
p = ev[ev.direction == "pump"]

print(f"coins={ev.pair.nunique()} pumps={len(p)} "
      f"dumps={(ev.direction == 'dump').sum()} signals={len(sig)}")
print(f"spike_before={p.had_volume_spike.mean():.0%} "
      f"silent={p.silent_volume_spike.mean():.0%} "
      f"lead={p.lead_time_h.median():.0f}h "
      f"retrace={p.retrace_frac.median():.0%}")
print(f"overall hit={sig.pumped.mean():.1%}\n")

order = ["mega", "large", "mid", "small", "micro", "tiny"]
print("by tier:")
print(sig.groupby("tier").pumped.agg(n="count", hit="mean")
      .round(3).reindex(order).to_string())

sig["zbin"] = pd.cut(sig.vol_z, [2, 3, 4, 99])
print("\nby spike strength:")
print(sig.groupby("zbin", observed=True).pumped
      .agg(n="count", hit="mean").round(3).to_string())

if "period" in sig.columns:
    print("\nby period (all signals):")
    print(sig.groupby("period").pumped.agg(n="count", hit="mean")
          .round(3).to_string())
    best = sig[(sig.vol_z >= 3) & sig.tier.isin(
        ["mid", "small", "micro", "tiny"])]
    print(f"\nscreener profile (z>=3, mid & below): "
          f"n={len(best)} hit={best.pumped.mean():.1%}")
    print(best.groupby("period").pumped.agg(n="count", hit="mean")
          .round(3).to_string())
