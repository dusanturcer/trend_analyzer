"""Detect quick price jumps (pumps) and drops (dumps) in hourly candles."""
import numpy as np
import pandas as pd

import config as C


def rolling_moves(close: pd.Series, window_h: int) -> pd.Series:
    """Max gain from the rolling min over the past `window_h` hours, per bar.

    move[t] = close[t] / min(close[t-window_h .. t]) - 1
    """
    roll_min = close.rolling(window_h, min_periods=2).min()
    return close / roll_min - 1


def detect_events(df: pd.DataFrame, threshold: float, window_h: int,
                  direction: str = "pump") -> list[dict]:
    """Find distinct events where price moved >= threshold within window_h hours.

    Returns list of dicts with start/peak/end indices and magnitudes.
    df must have columns open_time, close (sorted, hourly).
    """
    close = df["close"].reset_index(drop=True)
    if direction == "dump":
        # detect drops by inverting price: a dump on price = pump on 1/price
        close = 1.0 / close

    move = rolling_moves(close, window_h)
    hot = move >= threshold
    if not hot.any():
        return []

    events = []
    idx = np.flatnonzero(hot.values)
    # group consecutive/nearby hot bars into candidate events
    groups = np.split(idx, np.flatnonzero(np.diff(idx) > C.MIN_EVENT_GAP_H) + 1)

    for g in groups:
        seg_start, seg_end = g[0], g[-1]
        # peak = highest close in the hot segment (on transformed price)
        peak_i = int(close.iloc[seg_start:seg_end + 1].idxmax())
        # start = the rolling-min bar that produced the trigger move:
        lo = max(0, peak_i - window_h)
        start_i = int(close.iloc[lo:peak_i + 1].idxmin())
        if start_i >= peak_i:
            continue
        magnitude = float(close.iloc[peak_i] / close.iloc[start_i] - 1)
        if magnitude < threshold:
            continue
        # end = when price first retraces 50% of the move, or +72h, whichever first
        target = close.iloc[peak_i] - 0.5 * (close.iloc[peak_i] - close.iloc[start_i])
        end_i = min(peak_i + 72, len(close) - 1)
        after = close.iloc[peak_i:end_i + 1]
        hit = after[after <= target]
        if len(hit):
            end_i = int(hit.index[0])

        real_close = df["close"].reset_index(drop=True)
        sign = 1 if direction == "pump" else -1
        real_mag = float(real_close.iloc[peak_i] / real_close.iloc[start_i] - 1)
        events.append({
            "direction": direction,
            "start_idx": start_i, "peak_idx": peak_i, "end_idx": end_i,
            "start_time": df["open_time"].iloc[start_i],
            "peak_time": df["open_time"].iloc[peak_i],
            "duration_h": peak_i - start_i,
            "magnitude": sign * abs(real_mag),
            "abs_magnitude": abs(real_mag),
        })

    # dedupe events whose starts are within MIN_EVENT_GAP_H (keep biggest)
    events.sort(key=lambda e: e["start_idx"])
    deduped = []
    for e in events:
        if deduped and e["start_idx"] - deduped[-1]["start_idx"] < C.MIN_EVENT_GAP_H:
            if e["abs_magnitude"] > deduped[-1]["abs_magnitude"]:
                deduped[-1] = e
        else:
            deduped.append(e)
    return deduped


def retracement(df: pd.DataFrame, ev: dict, horizon_h: int = 72) -> dict:
    """How much of the move retraced within horizon_h after the peak."""
    close = df["close"].reset_index(drop=True)
    p_start, p_peak = close.iloc[ev["start_idx"]], close.iloc[ev["peak_idx"]]
    stop = min(ev["peak_idx"] + horizon_h, len(close) - 1)
    if stop <= ev["peak_idx"] or p_peak == p_start:
        return {"retrace_frac": np.nan, "hours_to_half_retrace": np.nan}
    after = close.iloc[ev["peak_idx"]:stop + 1]
    if ev["direction"] == "pump":
        worst = after.min()
        frac = float((p_peak - worst) / (p_peak - p_start))
        half_level = p_peak - 0.5 * (p_peak - p_start)
        hit = after[after <= half_level]
    else:
        worst = after.max()
        frac = float((worst - p_peak) / (p_start - p_peak))
        half_level = p_peak + 0.5 * (p_start - p_peak)
        hit = after[after >= half_level]
    hours = float(hit.index[0] - ev["peak_idx"]) if len(hit) else np.nan
    return {"retrace_frac": min(max(frac, 0.0), 2.0),
            "hours_to_half_retrace": hours}


def sweep_counts(df: pd.DataFrame) -> list[dict]:
    """Event counts for every (threshold, window) combination in the sweep grid."""
    rows = []
    for th in C.SWEEP_THRESHOLDS:
        for w in C.SWEEP_WINDOWS_H:
            n = len(detect_events(df, th, w, "pump"))
            rows.append({"threshold": th, "window_h": w, "n_pumps": n})
    return rows
