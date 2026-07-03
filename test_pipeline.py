"""End-to-end test on synthetic data with planted pumps.

    python -m pytest test_pipeline.py -q
"""
import json

import numpy as np
import pandas as pd

import config as C


def make_coin(rng, hours=183 * 24, planted_pumps=(), base_price=1.0):
    """Synthetic hourly klines. planted_pumps: list of (hour_idx, gain).

    Each planted pump gets a volume spike 6-12h BEFORE it starts.
    """
    t0 = pd.Timestamp("2026-01-01", tz="UTC")
    times = pd.date_range(t0, periods=hours, freq="h")
    ret = rng.normal(0, 0.004, hours)          # calm baseline
    vol_mult = np.ones(hours)

    for start, gain in planted_pumps:
        dur = 8
        ret[start:start + dur] += np.log1p(gain) / dur
        # decay afterwards
        ret[start + dur:start + dur + 24] -= np.log1p(gain) * 0.6 / 24
        # precursor volume spike, price still flat
        spike_at = start - rng.integers(6, 13)
        vol_mult[spike_at:spike_at + 3] *= 8.0
        vol_mult[start:start + dur] *= 5.0

    close = base_price * np.exp(np.cumsum(ret))
    open_ = np.roll(close, 1); open_[0] = base_price
    # diurnal volume pattern + noise
    hour = times.hour.values
    diurnal = 1 + 0.5 * np.sin(2 * np.pi * hour / 24)
    volume = rng.lognormal(10, 0.3, hours) * diurnal * vol_mult
    quote_volume = volume * close
    return pd.DataFrame({
        "open_time": times, "open": open_,
        "high": close * 1.002, "low": close * 0.998, "close": close,
        "volume": volume, "close_time": times + pd.Timedelta(hours=1),
        "quote_volume": quote_volume,
        "trades": (volume / 10).astype(int),
        "taker_buy_base": volume * 0.5, "taker_buy_quote": quote_volume * 0.5,
    })


def setup_synthetic(tmp_path, monkeypatch):
    data = tmp_path / "data"; klines = data / "klines"
    out = tmp_path / "output"
    klines.mkdir(parents=True)
    monkeypatch.setattr(C, "DATA_DIR", data)
    monkeypatch.setattr(C, "KLINES_DIR", klines)
    monkeypatch.setattr(C, "OUT_DIR", out)
    monkeypatch.setattr(C, "CHARTS_DIR", out / "charts")

    rng = np.random.default_rng(7)
    universe, planted = [], {}
    for i in range(6):
        pair = f"COIN{i}USDT"
        pumps = [(1200 + i * 300, 0.18), (3000 + i * 150, 0.25)]
        df = make_coin(rng, planted_pumps=pumps)
        df.to_parquet(klines / f"{pair}.parquet", index=False)
        planted[pair] = pumps
        universe.append({"symbol": f"COIN{i}", "name": f"Coin {i}",
                         "market_cap": 10**9 // (i + 1), "rank": i + 1,
                         "pair": pair})
    with open(data / "universe.json", "w") as f:
        json.dump(universe, f)
    return planted


def test_detection_finds_planted_pumps(tmp_path, monkeypatch):
    import detection as D
    planted = setup_synthetic(tmp_path, monkeypatch)
    for pair, pumps in planted.items():
        df = pd.read_parquet(C.KLINES_DIR / f"{pair}.parquet")
        evs = D.detect_events(df, 0.10, 24, "pump")
        starts = [e["start_idx"] for e in evs]
        for hour_idx, _gain in pumps:
            assert any(abs(s - hour_idx) <= 24 for s in starts), \
                f"{pair}: planted pump at {hour_idx} not detected (found {starts})"


def test_precursor_features_see_the_spike(tmp_path, monkeypatch):
    import detection as D
    import features as F
    planted = setup_synthetic(tmp_path, monkeypatch)
    pair = "COIN0USDT"
    df = F.add_baselines(pd.read_parquet(C.KLINES_DIR / f"{pair}.parquet"))
    evs = D.detect_events(df, 0.10, 24, "pump")
    hits = 0
    for ev in evs:
        feats = F.window_features(df, ev["start_idx"])
        if feats and feats["had_volume_spike"]:
            hits += 1
    assert hits >= 1, "planted volume spikes not seen in precursor window"


def test_full_pipeline_produces_report(tmp_path, monkeypatch):
    setup_synthetic(tmp_path, monkeypatch)
    import analyze
    analyze.main()
    assert (C.OUT_DIR / "report.html").exists()
    assert (C.OUT_DIR / "events.csv").exists()
    ev = pd.read_csv(C.OUT_DIR / "events.csv")
    assert (ev["direction"] == "pump").sum() >= 6
    html = (C.OUT_DIR / "report.html").read_text(encoding="utf-8")
    assert "Predictive value" in html
