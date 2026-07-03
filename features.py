"""Precursor feature extraction: what did volume/price do BEFORE an event?"""
import numpy as np
import pandas as pd

import config as C


def add_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """Add hour-of-day-adjusted volume z-scores and volatility columns.

    Crypto volume is strongly diurnal, so the baseline for 14:00 UTC is the
    trailing BASELINE_DAYS of 14:00 UTC bars — not all bars.
    """
    df = df.reset_index(drop=True).copy()
    df["hour"] = df["open_time"].dt.hour
    df["log_vol"] = np.log1p(df["quote_volume"])

    # trailing mean/std of log volume for the same hour of day
    g = df.groupby("hour")["log_vol"]
    mean = g.transform(lambda s: s.rolling(C.BASELINE_DAYS, min_periods=7)
                       .mean().shift(1))
    std = g.transform(lambda s: s.rolling(C.BASELINE_DAYS, min_periods=7)
                      .std().shift(1))
    df["vol_z"] = (df["log_vol"] - mean) / std.replace(0, np.nan)

    # taker buy ratio (buy pressure) and its trailing baseline
    df["buy_ratio"] = (df["taker_buy_quote"] / df["quote_volume"]).clip(0, 1)
    df["buy_ratio_base"] = df["buy_ratio"].rolling(
        24 * C.BASELINE_DAYS, min_periods=48).mean().shift(1)

    # trade count z-score (same diurnal treatment)
    df["log_trades"] = np.log1p(df["trades"])
    gt = df.groupby("hour")["log_trades"]
    tmean = gt.transform(lambda s: s.rolling(C.BASELINE_DAYS, min_periods=7)
                         .mean().shift(1))
    tstd = gt.transform(lambda s: s.rolling(C.BASELINE_DAYS, min_periods=7)
                        .std().shift(1))
    df["trades_z"] = (df["log_trades"] - tmean) / tstd.replace(0, np.nan)

    # hourly returns and rolling 24h realized volatility
    df["ret"] = df["close"].pct_change()
    df["rvol_24h"] = df["ret"].rolling(24, min_periods=12).std()
    df["rvol_pctl"] = df["rvol_24h"].rolling(24 * C.BASELINE_DAYS, min_periods=100)\
        .rank(pct=True) * 100
    return df


def _slope(y: np.ndarray) -> float:
    y = y[~np.isnan(y)]
    if len(y) < 3:
        return np.nan
    x = np.arange(len(y), dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def window_features(df: pd.DataFrame, anchor_idx: int) -> dict:
    """Features of the PRE_WINDOW_H hours strictly before anchor_idx.

    df must already have add_baselines() applied.
    """
    lo = anchor_idx - C.PRE_WINDOW_H
    if lo < 0:
        return {}
    w = df.iloc[lo:anchor_idx]
    w24 = w.iloc[-24:]
    w12 = w.iloc[-12:]
    w6 = w.iloc[-6:]

    vz = w["vol_z"]
    feats = {
        # --- volume anomaly ---
        "max_vol_z_48h": float(vz.max()),
        "max_vol_z_24h": float(w24["vol_z"].max()),
        "mean_vol_z_24h": float(w24["vol_z"].mean()),
        "n_spike_hours_24h": int((w24["vol_z"] >= C.VOLUME_SPIKE_Z).sum()),
        "had_volume_spike": bool((vz >= C.VOLUME_SPIKE_Z).any()),
        # --- volume ramp (slope of z-score over trailing windows) ---
        "vol_ramp_24h": _slope(w24["vol_z"].values),
        "vol_ramp_12h": _slope(w12["vol_z"].values),
        "vol_ramp_6h": _slope(w6["vol_z"].values),
        # --- buy pressure ---
        "buy_ratio_24h": float(w24["buy_ratio"].mean()),
        "buy_ratio_delta": float(w24["buy_ratio"].mean()
                                 - w24["buy_ratio_base"].mean()),
        # --- trade count anomaly ---
        "max_trades_z_24h": float(w24["trades_z"].max()),
        # --- price behavior before the move ---
        "pre_ret_24h": float(w["close"].iloc[-1] / w24["close"].iloc[0] - 1)
                       if len(w24) else np.nan,
        "rvol_pctl_pre": float(w["rvol_pctl"].iloc[-1]),
        "was_coiling": bool(w["rvol_pctl"].iloc[-1] <= C.QUIET_VOL_PCTL),
    }

    # lead time: hours between FIRST volume spike in the window and the anchor
    spikes = np.flatnonzero((vz >= C.VOLUME_SPIKE_Z).values)
    feats["lead_time_h"] = float(len(vz) - spikes[0]) if len(spikes) else np.nan

    # was the volume spike "silent"? (spike happened while |price move| < 2%)
    silent = False
    for s in spikes:
        j = lo + s
        p0 = df["close"].iloc[max(0, j - 3)]
        p1 = df["close"].iloc[j]
        if abs(p1 / p0 - 1) < 0.02:
            silent = True
            break
    feats["silent_volume_spike"] = silent
    return feats


def event_shape(df: pd.DataFrame, ev: dict, pre_h: int = 24, post_h: int = 24):
    """Normalized price trajectory around an event start, for clustering."""
    lo, hi = ev["start_idx"] - pre_h, ev["start_idx"] + post_h
    if lo < 0 or hi >= len(df):
        return None
    seg = df["close"].iloc[lo:hi + 1].values
    return seg / seg[pre_h] - 1  # 0 at event start
