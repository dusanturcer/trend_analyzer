"""Main analysis: detect events, extract precursors, compare vs control group,
measure predictive value of volume spikes, cluster event shapes, write report.

    python analyze.py
"""
import json
import random
from collections import defaultdict

import numpy as np
import pandas as pd

import config as C
import detection as D
import features as F
from report import write_report


def load_universe():
    with open(C.DATA_DIR / "universe.json") as f:
        universe = json.load(f)
    caps = sorted([c["market_cap"] for c in universe], reverse=True)
    # market-cap tiers: mega = top 20, large = 21-75, mid = 76-150, small = rest
    for c in universe:
        r = c["rank"]
        c["tier"] = ("mega" if r <= 20 else "large" if r <= 75
                     else "mid" if r <= 150 else "small")
    return {c["pair"]: c for c in universe
            if (C.KLINES_DIR / f"{c['pair']}.parquet").exists()}


def forward_max_gain(close: pd.Series, horizon_h: int) -> pd.Series:
    """max(close[t+1..t+h]) / close[t] - 1  (future best gain)."""
    fwd_max = close[::-1].rolling(horizon_h, min_periods=1).max()[::-1].shift(-1)
    return fwd_max / close - 1


def btc_context(btc: pd.DataFrame | None, t) -> float:
    """BTC 24h return ending at time t (market context)."""
    if btc is None:
        return np.nan
    i = btc["open_time"].searchsorted(t)
    if i < 25 or i >= len(btc):
        return np.nan
    return float(btc["close"].iloc[i - 1] / btc["close"].iloc[i - 25] - 1)


def analyze_coin(pair, meta, btc, rng):
    df = pd.read_parquet(C.KLINES_DIR / f"{pair}.parquet")
    df = F.add_baselines(df)

    events = []
    directions = ["pump"] + (["dump"] if C.DETECT_DUMPS else [])
    all_evs = []
    for direction in directions:
        all_evs += D.detect_events(df, C.PUMP_THRESHOLD, C.PUMP_WINDOW_H, direction)

    for ev in all_evs:
        feats = F.window_features(df, ev["start_idx"])
        if not feats:
            continue
        row = {
            "pair": pair, "coin": meta["symbol"], "tier": meta["tier"],
            "rank": meta["rank"], **ev, **feats,
            **D.retracement(df, ev),
            "btc_ret_24h": btc_context(btc, ev["start_time"]),
            "start_hour_utc": int(ev["start_time"].hour),
            "start_dow": int(ev["start_time"].dayofweek),
        }
        row.pop("start_idx"); row.pop("peak_idx"); row.pop("end_idx")
        events.append(row)

    # ---- control group: random anchors far from any event start ----
    ev_starts = {e["start_idx"] for e in all_evs}
    controls = []
    lo, hi = C.PRE_WINDOW_H + 24 * C.BASELINE_DAYS, len(df) - C.PUMP_WINDOW_H - 1
    if hi > lo:
        want = max(len(all_evs), 2) * C.N_CONTROL_PER_EVENT
        tries = 0
        while len(controls) < want and tries < want * 20:
            tries += 1
            i = rng.randint(lo, hi)
            if any(abs(i - s) < 48 for s in ev_starts):
                continue
            feats = F.window_features(df, i)
            if feats:
                controls.append({"pair": pair, "tier": meta["tier"], **feats})

    # ---- signal scan: every silent volume spike -> did a pump follow? ----
    fwd = forward_max_gain(df["close"], C.PUMP_WINDOW_H)
    ret3h = df["close"].pct_change(3).abs()
    spike = ((df["vol_z"] >= C.VOLUME_SPIKE_Z) & (ret3h < 0.02)).values
    # keep first hour of each spike run only
    spike[1:] &= ~spike[:-1]
    signals = []
    valid = slice(24 * 7, len(df) - C.PUMP_WINDOW_H)
    for i in np.flatnonzero(spike[valid]) + valid.start:
        signals.append({"pair": pair, "tier": meta["tier"],
                        "vol_z": float(df["vol_z"].iloc[i]),
                        "fwd_gain": float(fwd.iloc[i]),
                        "pumped": bool(fwd.iloc[i] >= C.PUMP_THRESHOLD)})
    base_rate = float((fwd.iloc[valid] >= C.PUMP_THRESHOLD).mean())

    return events, controls, signals, base_rate, D.sweep_counts(df), df, all_evs


def cluster_shapes(shapes, k=4):
    from sklearn.cluster import KMeans
    if len(shapes) < k * 5:
        return None
    X = np.array([s["shape"] for s in shapes])
    X = np.nan_to_num(X / (np.abs(X).max(axis=1, keepdims=True) + 1e-12))
    km = KMeans(n_clusters=k, n_init=10, random_state=C.CONTROL_SEED).fit(X)
    return {"labels": km.labels_,
            "centroids": km.cluster_centers_,
            "sizes": np.bincount(km.labels_)}


def epoch_matrix(dfs_events, pre_h=48, post_h=12):
    """Stack vol_z trajectories around pump starts (superimposed epoch analysis)."""
    rows = []
    for df, evs in dfs_events:
        for ev in evs:
            if ev["direction"] != "pump":
                continue
            lo, hi = ev["start_idx"] - pre_h, ev["start_idx"] + post_h
            if lo < 0 or hi >= len(df):
                continue
            rows.append(df["vol_z"].iloc[lo:hi + 1].values)
    return np.array(rows) if rows else None


def main():
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    C.CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(C.CONTROL_SEED)

    universe = load_universe()
    print(f"Analyzing {len(universe)} coins...")

    btc = None
    if (C.KLINES_DIR / "BTCUSDT.parquet").exists():
        btc = pd.read_parquet(C.KLINES_DIR / "BTCUSDT.parquet")

    events, controls, signals, sweep_rows, shapes = [], [], [], [], []
    base_rates, dfs_events, chart_candidates = [], [], []

    for n, (pair, meta) in enumerate(universe.items(), 1):
        if n % 25 == 0:
            print(f"  {n}/{len(universe)}")
        try:
            evs, ctr, sig, br, sweep, df, all_evs = analyze_coin(
                pair, meta, btc, rng)
        except Exception as e:
            print(f"  {pair} failed: {e}")
            continue
        events += evs
        controls += ctr
        signals += sig
        base_rates.append(br)
        for r in sweep:
            sweep_rows.append({"pair": pair, **r})
        dfs_events.append((df, all_evs))
        for ev in all_evs:
            if ev["direction"] != "pump":
                continue
            chart_candidates.append((ev["abs_magnitude"], pair, df, ev))
            shp = F.event_shape(df, ev)
            if shp is not None:
                shapes.append({"pair": pair, "shape": shp,
                               "magnitude": ev["abs_magnitude"]})

    ev_df = pd.DataFrame(events)
    ctl_df = pd.DataFrame(controls)
    sig_df = pd.DataFrame(signals)
    sweep_df = (pd.DataFrame(sweep_rows)
                .groupby(["threshold", "window_h"])["n_pumps"]
                .agg(["sum", "mean"]).round(2).reset_index()
                .rename(columns={"sum": "total_events", "mean": "avg_per_coin"}))

    ev_df.to_csv(C.OUT_DIR / "events.csv", index=False)
    sweep_df.to_csv(C.OUT_DIR / "sweep.csv", index=False)
    sig_df.to_csv(C.OUT_DIR / "signals.csv", index=False)

    epoch = epoch_matrix(dfs_events)
    clusters = cluster_shapes(shapes)
    chart_candidates.sort(key=lambda t: -t[0])

    write_report(ev_df, ctl_df, sig_df, sweep_df,
                 float(np.mean(base_rates)) if base_rates else np.nan,
                 epoch, clusters, shapes, chart_candidates[:12])

    print(f"\nDone. {len(ev_df)} events "
          f"({(ev_df['direction'] == 'pump').sum()} pumps, "
          f"{(ev_df['direction'] == 'dump').sum()} dumps) "
          f"across {ev_df['pair'].nunique()} coins.")
    print(f"Report: {C.OUT_DIR / 'report.html'}")


if __name__ == "__main__":
    main()
