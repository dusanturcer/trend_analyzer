"""Extra technical indicators, computed per bar on hourly candles.

Used to test which indicators correlate with E-combo trade outcomes.
All values are designed to be comparable ACROSS coins (ratios, percentile
ranks) rather than absolute prices.
"""
import numpy as np
import pandas as pd

WIN = 720  # 30d of hourly bars for percentile ranks

INDICATOR_COLS = [
    "rsi14", "bbw_pctl", "dist_30d_high", "dist_30d_low", "obv_chg_pctl",
    "macd_rel", "atr_pctl", "vwap7_dist", "ret_7d", "ret_24h",
    "spike_hours_24h", "buy_ratio", "hour_utc", "dow",
]


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """df: hourly candles AFTER features.add_baselines(). Adds indicator cols."""
    df = df.copy()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # RSI-14 (Wilder)
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
    df["rsi14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))

    # Bollinger band width (20) as percentile of its own 30d history
    ma, sd = c.rolling(20).mean(), c.rolling(20).std()
    bbw = (4 * sd / ma)
    df["bbw_pctl"] = bbw.rolling(WIN, min_periods=100).rank(pct=True) * 100

    # distance from 30d high / low (breakout proximity)
    df["dist_30d_high"] = c / c.rolling(WIN, min_periods=100).max() - 1
    df["dist_30d_low"] = c / c.rolling(WIN, min_periods=100).min() - 1

    # OBV 24h change, percentile-ranked (accumulation pressure)
    obv = (np.sign(d).fillna(0) * v).cumsum()
    df["obv_chg_pctl"] = (obv - obv.shift(24)).rolling(
        WIN, min_periods=100).rank(pct=True) * 100

    # MACD histogram relative to price
    ema12, ema26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    macd = ema12 - ema26
    df["macd_rel"] = (macd - macd.ewm(span=9).mean()) / c

    # ATR-14 percentile (volatility state)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()],
                   axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, min_periods=14).mean()
    df["atr_pctl"] = atr.rolling(WIN, min_periods=100).rank(pct=True) * 100

    # distance from 7d volume-weighted average price
    qv = df["quote_volume"]
    df["vwap7_dist"] = c / (qv.rolling(168).sum()
                            / v.rolling(168).sum().replace(0, np.nan)) - 1

    # momentum context
    df["ret_7d"] = c.pct_change(168)
    df["ret_24h"] = c.pct_change(24)

    # spike persistence (from baseline vol_z)
    df["spike_hours_24h"] = (df["vol_z"] >= 2).rolling(24).sum()

    # time of day / week
    df["hour_utc"] = df["open_time"].dt.hour
    df["dow"] = df["open_time"].dt.dayofweek
    return df
