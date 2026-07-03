"""Build output/report.html: stats tables + embedded charts."""
import base64
import io

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = [
    "Segoe UI", "Arial", "Calibri", "DejaVu Sans", "sans-serif"]
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import config as C

FEATS = [
    ("max_vol_z_24h", "Max volume z-score, last 24h"),
    ("max_vol_z_48h", "Max volume z-score, last 48h"),
    ("mean_vol_z_24h", "Mean volume z-score, last 24h"),
    ("n_spike_hours_24h", f"Hours with vol z≥{C.VOLUME_SPIKE_Z}, last 24h"),
    ("vol_ramp_24h", "Volume ramp slope, 24h"),
    ("vol_ramp_6h", "Volume ramp slope, 6h"),
    ("buy_ratio_24h", "Taker buy ratio, 24h"),
    ("buy_ratio_delta", "Buy-ratio shift vs baseline"),
    ("max_trades_z_24h", "Max trade-count z, 24h"),
    ("rvol_pctl_pre", "Pre-event volatility percentile"),
    ("pre_ret_24h", "Price return, prior 24h"),
]


def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def img(fig, caption=""):
    return (f'<figure><img src="data:image/png;base64,{fig_to_b64(fig)}">'
            f"<figcaption>{caption}</figcaption></figure>")


def compare_table(pumps: pd.DataFrame, ctl: pd.DataFrame) -> str:
    rows = []
    for col, label in FEATS:
        a = pumps[col].dropna()
        b = ctl[col].dropna() if col in ctl else pd.Series(dtype=float)
        if len(a) < 5 or len(b) < 5:
            continue
        try:
            p = stats.mannwhitneyu(a, b, alternative="two-sided").pvalue
        except ValueError:
            p = np.nan
        rows.append({
            "Feature": label,
            "Before pumps (median)": round(float(a.median()), 3),
            "Control windows (median)": round(float(b.median()), 3),
            "p-value": f"{p:.1e}" if p == p else "n/a",
            "Significant": "YES" if p < 0.01 else "no",
        })
    return pd.DataFrame(rows).to_html(index=False, escape=False)


def rate_block(name, n, k, base):
    rate = k / n if n else np.nan
    lift = rate / base if base else np.nan
    return {"Segment": name, "Signals": n, "Followed by pump": k,
            "Hit rate": f"{rate:.1%}" if n else "n/a",
            "Base rate": f"{base:.1%}",
            "Lift": f"{lift:.1f}x" if n else "n/a"}


def event_chart(pair, df, ev):
    lo = max(0, ev["start_idx"] - 72)
    hi = min(len(df) - 1, ev["peak_idx"] + 48)
    w = df.iloc[lo:hi + 1]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 4.5), sharex=True,
                                   height_ratios=[2, 1])
    ax1.plot(w["open_time"], w["close"], lw=1)
    ax1.axvspan(ev["start_time"], ev["peak_time"], alpha=0.15, color="green")
    ax1.set_title(f"{pair}: {ev['abs_magnitude']:+.1%} in {ev['duration_h']}h "
                  f"({ev['start_time']:%Y-%m-%d})", fontsize=10)
    ax2.bar(w["open_time"], w["vol_z"].clip(-1, None), width=0.03,
            color=np.where(w["vol_z"] >= C.VOLUME_SPIKE_Z, "red", "gray"))
    ax2.axhline(C.VOLUME_SPIKE_Z, color="red", lw=0.7, ls="--")
    ax2.set_ylabel("vol z")
    fig.autofmt_xdate()
    return fig


def write_report(ev_df, ctl_df, sig_df, sweep_df, base_rate,
                 epoch, clusters, shapes, chart_candidates):
    pumps = ev_df[ev_df["direction"] == "pump"] if len(ev_df) else ev_df
    dumps = ev_df[ev_df["direction"] == "dump"] if len(ev_df) else ev_df
    parts = []

    # ---------------- headline ----------------
    spike_share = pumps["had_volume_spike"].mean() if len(pumps) else np.nan
    ctl_spike_share = ctl_df["had_volume_spike"].mean() if len(ctl_df) else np.nan
    silent_share = pumps["silent_volume_spike"].mean() if len(pumps) else np.nan
    parts.append(f"""
    <h1>Crypto Pump Precursor Analysis</h1>
    <p class="meta">{len(pumps)} pumps / {len(dumps)} dumps across
    {ev_df['pair'].nunique() if len(ev_df) else 0} coins &middot;
    definition: &ge;{C.PUMP_THRESHOLD:.0%} within {C.PUMP_WINDOW_H}h &middot;
    control group: {len(ctl_df)} random windows</p>
    <div class="cards">
      <div class="card"><b>{spike_share:.0%}</b> of pumps had a volume spike
        (z&ge;{C.VOLUME_SPIKE_Z}) in the prior 48h</div>
      <div class="card"><b>{ctl_spike_share:.0%}</b> of random control windows
        did (the honest comparison)</div>
      <div class="card"><b>{silent_share:.0%}</b> of pumps were preceded by a
        <i>silent</i> spike (volume up, price still flat)</div>
    </div>""")

    # ---------------- feature comparison ----------------
    if len(pumps) and len(ctl_df):
        parts.append("<h2>1. What looks different before a pump?</h2>"
                     "<p>Median precursor features before pumps vs random "
                     "control windows (Mann-Whitney U test).</p>")
        parts.append(compare_table(pumps, ctl_df))

    # ---------------- predictive value ----------------
    if len(sig_df):
        parts.append(f"""<h2>2. Predictive value of the signal</h2>
        <p>Every "silent volume spike" (vol z&ge;{C.VOLUME_SPIKE_Z}, price move
        &lt;2% over 3h) in the whole dataset: how often did a
        &ge;{C.PUMP_THRESHOLD:.0%} pump follow within {C.PUMP_WINDOW_H}h?</p>""")
        rows = [rate_block("All coins", len(sig_df),
                           int(sig_df["pumped"].sum()), base_rate)]
        for tier in ["mega", "large", "mid", "small"]:
            s = sig_df[sig_df["tier"] == tier]
            rows.append(rate_block(tier, len(s), int(s["pumped"].sum()),
                                   base_rate))
        for z_lo, z_hi in [(2, 3), (3, 4), (4, 99)]:
            s = sig_df[(sig_df["vol_z"] >= z_lo) & (sig_df["vol_z"] < z_hi)]
            rows.append(rate_block(f"spike z in [{z_lo},{z_hi})", len(s),
                                   int(s["pumped"].sum()), base_rate))
        parts.append(pd.DataFrame(rows).to_html(index=False))
        parts.append("<p><i>Lift &gt; 1x means the signal beats picking a "
                     "random hour. Hit rate is the false-positive-adjusted "
                     "reality check.</i></p>")

    # ---------------- epoch chart ----------------
    if epoch is not None and len(epoch):
        t = np.arange(-48, epoch.shape[1] - 48)
        fig, ax = plt.subplots(figsize=(8, 3.5))
        med = np.nanmedian(epoch, axis=0)
        q1, q3 = np.nanpercentile(epoch, [25, 75], axis=0)
        ax.plot(t, med, lw=2)
        ax.fill_between(t, q1, q3, alpha=0.2)
        ax.axvline(0, color="green", ls="--", lw=1)
        ax.axhline(C.VOLUME_SPIKE_Z, color="red", ls=":", lw=1)
        ax.set_xlabel("hours relative to pump start")
        ax.set_ylabel("volume z-score")
        parts.append("<h2>3. Average volume behavior around pump start</h2>")
        parts.append(img(fig, "Median volume z-score (IQR shaded) across all "
                              "pumps. Green line = pump start."))

    # ---------------- distributions ----------------
    if len(pumps):
        fig, axes = plt.subplots(2, 2, figsize=(10, 6))
        pumps["lead_time_h"].dropna().hist(bins=24, ax=axes[0, 0])
        axes[0, 0].set_title("Lead time: 1st volume spike → pump start (h)")
        pumps["abs_magnitude"].hist(bins=30, ax=axes[0, 1])
        axes[0, 1].set_title("Pump magnitude")
        pumps["start_hour_utc"].hist(bins=24, ax=axes[1, 0])
        axes[1, 0].set_title("Pump start hour (UTC)")
        pumps["retrace_frac"].dropna().hist(bins=25, ax=axes[1, 1])
        axes[1, 1].set_title("Retracement fraction within 72h of peak")
        fig.tight_layout()
        parts.append("<h2>4. Event anatomy</h2>")
        parts.append(img(fig))
        med_r = pumps["retrace_frac"].median()
        full_r = (pumps["retrace_frac"] >= 0.9).mean()
        parts.append(f"<p>Median pump retraces <b>{med_r:.0%}</b> of its move "
                     f"within 72h; <b>{full_r:.0%}</b> retrace almost fully "
                     f"(&ge;90%). Chasing after the peak is usually late.</p>")

    # ---------------- clusters ----------------
    if clusters is not None:
        t = np.arange(-24, len(clusters["centroids"][0]) - 24)
        fig, ax = plt.subplots(figsize=(8, 3.5))
        for i, c in enumerate(clusters["centroids"]):
            ax.plot(t, c, label=f"cluster {i} (n={clusters['sizes'][i]})")
        ax.axvline(0, color="k", ls="--", lw=0.7)
        ax.legend(fontsize=8)
        ax.set_xlabel("hours relative to pump start")
        ax.set_ylabel("normalized price")
        parts.append("<h2>5. Pump shape families</h2>")
        parts.append(img(fig, "K-means centroids of normalized price paths "
                              "(24h before → 24h after pump start)."))

    # ---------------- sweep ----------------
    parts.append("<h2>6. How definition changes event counts</h2>")
    parts.append(sweep_df.to_html(index=False))

    # ---------------- tier / context breakdowns ----------------
    if len(pumps):
        by_tier = (pumps.groupby("tier")
                   .agg(n=("pair", "size"),
                        median_magnitude=("abs_magnitude", "median"),
                        spike_share=("had_volume_spike", "mean"),
                        median_retrace=("retrace_frac", "median"))
                   .round(3).reset_index())
        parts.append("<h2>7. By market-cap tier</h2>")
        parts.append(by_tier.to_html(index=False))
        if pumps["btc_ret_24h"].notna().any():
            up = pumps[pumps["btc_ret_24h"] > 0.01]
            dn = pumps[pumps["btc_ret_24h"] < -0.01]
            flat = pumps[pumps["btc_ret_24h"].abs() <= 0.01]
            parts.append(f"<p>BTC context at pump start: {len(up)} during BTC "
                         f"up-moves, {len(flat)} during flat BTC, {len(dn)} "
                         f"during BTC down-moves.</p>")

    # ---------------- example charts ----------------
    if chart_candidates:
        parts.append("<h2>8. Largest pumps, close up</h2>")
        for mag, pair, df, ev in chart_candidates:
            parts.append(img(event_chart(pair, df, ev)))

    html = f"""<!doctype html><meta charset="utf-8">
<title>Crypto Pump Precursor Analysis</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;
      padding:0 1em;color:#1a1a2e}}
 h1{{font-size:1.6em}} h2{{margin-top:1.6em;border-bottom:1px solid #ddd}}
 table{{border-collapse:collapse;font-size:.85em;margin:1em 0}}
 th,td{{border:1px solid #ccc;padding:4px 9px;text-align:right}}
 th{{background:#f0f0f5}} td:first-child,th:first-child{{text-align:left}}
 img{{max-width:100%}} figure{{margin:1em 0}}
 figcaption{{font-size:.8em;color:#666}}
 .meta{{color:#666;font-size:.9em}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap}}
 .card{{background:#f4f6fb;border-radius:8px;padding:12px 16px;flex:1;
       min-width:200px;font-size:.9em}}
 .card b{{font-size:1.5em;display:block}}
</style>
{''.join(parts)}
<p class="meta">Generated by trend_analyzer. Statistical analysis of
historical data — not financial advice.</p>"""
    with open(C.OUT_DIR / "report.html", "w", encoding="utf-8") as f:
        f.write(html)
