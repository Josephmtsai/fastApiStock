"""Technical indicator calculations for stock data.

All functions are pure: they accept a yfinance history DataFrame and return
typed results with None for any indicator that cannot be computed due to
insufficient history.
"""

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class IndicatorResult:
    """Computed technical indicators from a stock's price history.

    Attributes:
        rsi: RSI(14); None when fewer than 15 rows available.
        macd: MACD line (EMA12 - EMA26); None when history < 35 rows.
        macd_signal: MACD signal line EMA(9); None when history < 35 rows.
        macd_hist: MACD histogram (macd - signal); None when history < 35 rows.
        ma20: 20-day simple moving average; None when history < 20 rows.
        ma50: 50-day simple moving average; None when history < 50 rows.
        bb_upper: Bollinger upper band (20, 2σ); None when history < 20 rows.
        bb_mid: Bollinger middle band (MA20); None when history < 20 rows.
        bb_lower: Bollinger lower band (20, 2σ); None when history < 20 rows.
        volume_today: Latest day trading volume.
        volume_avg20: 20-day average volume.
        week52_high: Maximum high price in available history.
        week52_low: Minimum low price in available history.
    """

    rsi: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    ma20: float | None
    ma50: float | None
    bb_upper: float | None
    bb_mid: float | None
    bb_lower: float | None
    volume_today: int
    volume_avg20: int
    week52_high: float | None
    week52_low: float | None


@dataclass
class ScoreResult:
    """Technical analysis verdict derived from indicator scoring.

    Attributes:
        score: Aggregate score in the range -8 to +8.
        verdict: Human-readable verdict string.
        bull_reasons: List of bullish signal descriptions.
        bear_reasons: List of bearish signal descriptions.
    """

    score: int
    verdict: str
    bull_reasons: list[str]
    bear_reasons: list[str]


def _safe(value: float) -> float | None:
    """Return value unless it is NaN or Inf, in which case return None.

    Args:
        value: Candidate float.

    Returns:
        The value if finite, otherwise None.
    """
    return None if (math.isnan(value) or math.isinf(value)) else value


def _rsi(series: pd.Series, window: int = 14) -> float | None:  # type: ignore[type-arg]
    """Compute RSI using exponential weighted moving average of gains/losses.

    Args:
        series: Close price series.
        window: RSI period (default 14).

    Returns:
        RSI value rounded to 2 decimal places, or None if history is too short.
    """
    if len(series) < window + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
    last_loss = float(avg_loss.iloc[-1])
    if last_loss == 0.0:
        return 100.0
    rs = float(avg_gain.iloc[-1]) / last_loss
    return round(100.0 - 100.0 / (1.0 + rs), 2)


def _macd(
    series: pd.Series,  # type: ignore[type-arg]
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """Compute MACD line, signal line, and histogram.

    Args:
        series: Close price series.
        fast: Fast EMA period.
        slow: Slow EMA period.
        signal: Signal EMA period.

    Returns:
        Tuple of (macd_line, signal_line, histogram) or (None, None, None)
        when history is too short.
    """
    if len(series) < slow + signal:
        return None, None, None
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return (
        round(float(macd_line.iloc[-1]), 4),
        round(float(signal_line.iloc[-1]), 4),
        round(float(hist.iloc[-1]), 4),
    )


def _bollinger(
    series: pd.Series,  # type: ignore[type-arg]
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    """Compute Bollinger Bands (upper, middle, lower).

    Args:
        series: Close price series.
        window: Rolling window (default 20).
        num_std: Number of standard deviations (default 2.0).

    Returns:
        Tuple of (upper, mid, lower) rounded to 2 dp, or (None, None, None).
    """
    if len(series) < window:
        return None, None, None
    ma = series.rolling(window).mean()
    std = series.rolling(window).std()
    last_ma = _safe(float(ma.iloc[-1]))
    last_std = _safe(float(std.iloc[-1]))
    if last_ma is None or last_std is None:
        return None, None, None
    return (
        round(last_ma + num_std * last_std, 2),
        round(last_ma, 2),
        round(last_ma - num_std * last_std, 2),
    )


def calculate(hist: pd.DataFrame) -> IndicatorResult:
    """Compute all technical indicators from a yfinance history DataFrame.

    Args:
        hist: DataFrame with columns Close, High, Low, Volume indexed by date.
            Expects at least 1 row; indicators requiring more rows return None.

    Returns:
        Populated IndicatorResult; insufficient-history fields are None.
    """
    close = hist['Close']
    volume = hist['Volume']
    high = hist['High']
    low = hist['Low']

    ma20_val = (
        _safe(float(close.rolling(20).mean().iloc[-1])) if len(close) >= 20 else None
    )
    ma50_val = (
        _safe(float(close.rolling(50).mean().iloc[-1])) if len(close) >= 50 else None
    )
    bb_upper, bb_mid, bb_lower = _bollinger(close)
    rsi_val = _rsi(close)
    macd_val, macd_sig, macd_hist_val = _macd(close)

    vol_today = int(volume.iloc[-1]) if not math.isnan(float(volume.iloc[-1])) else 0
    raw_avg = (
        float(volume.rolling(20).mean().iloc[-1])
        if len(volume) >= 20
        else float(volume.mean())
    )
    vol_avg20 = int(raw_avg) if not math.isnan(raw_avg) else 0

    w52h = round(float(high.max()), 2) if len(high) > 0 else None
    w52l = round(float(low.min()), 2) if len(low) > 0 else None

    return IndicatorResult(
        rsi=rsi_val,
        macd=macd_val,
        macd_signal=macd_sig,
        macd_hist=macd_hist_val,
        ma20=ma20_val,
        ma50=ma50_val,
        bb_upper=bb_upper,
        bb_mid=bb_mid,
        bb_lower=bb_lower,
        volume_today=vol_today,
        volume_avg20=vol_avg20,
        week52_high=w52h,
        week52_low=w52l,
    )


def score_stock(
    price: float, change_pct: float, indicators: IndicatorResult
) -> ScoreResult:
    """Produce a technical analysis verdict from indicator values.

    Scoring range -8 to +8; verdict: ≥+3 → '看漲', ≤-3 → '看跌', else '中性觀望'.

    Args:
        price: Current price.
        change_pct: Percentage change vs previous close.
        indicators: Computed IndicatorResult for the stock.

    Returns:
        ScoreResult with verdict, score, and annotated reason lists.
    """
    score = 0
    bull: list[str] = []
    bear: list[str] = []

    rsi = indicators.rsi
    if rsi is not None:
        if rsi < 30:
            score += 2
            bull.append(f'RSI={rsi:.0f} 嚴重超賣，反彈機率高')
        elif rsi < 40:
            score += 1
            bull.append(f'RSI={rsi:.0f} 偏超賣，有支撐潛力')
        elif rsi > 70:
            score -= 2
            bear.append(f'RSI={rsi:.0f} 嚴重超買，回調風險高')
        elif rsi > 60:
            score -= 1
            bear.append(f'RSI={rsi:.0f} 偏超買，動能可能減弱')

    macd_h = indicators.macd_hist
    macd_v = indicators.macd
    if macd_h is not None:
        if macd_h > 0 and macd_v is not None and macd_v > 0:
            score += 2
            bull.append('MACD 金叉且在零軸上方，多頭趨勢明確')
        elif macd_h > 0:
            score += 1
            bull.append('MACD 柱狀轉正（金叉），動能翻多')
        elif macd_h < 0 and macd_v is not None and macd_v < 0:
            score -= 2
            bear.append('MACD 死叉且在零軸下方，空頭趨勢明確')
        elif macd_h < 0:
            score -= 1
            bear.append('MACD 柱狀為負（死叉），動能偏空')

    if indicators.ma20 is not None:
        if price > indicators.ma20:
            score += 1
            bull.append('站上 MA20 短期均線，趨勢向上')
        else:
            score -= 1
            bear.append('跌破 MA20 短期均線，短線走弱')

    if indicators.ma50 is not None:
        if price > indicators.ma50:
            score += 1
            bull.append('站上 MA50 中期均線，中期趨勢健康')
        else:
            score -= 1
            bear.append('跌破 MA50 中期均線，中期趨勢走弱')

    bb_u = indicators.bb_upper
    bb_l = indicators.bb_lower
    if bb_u is not None and bb_l is not None:
        bb_range = bb_u - bb_l
        if bb_range > 0:
            bb_pos = (price - bb_l) / bb_range
            if bb_pos < 0.15:
                score += 1
                bull.append('價格接近布林下軌，超賣反彈機率增加')
            elif bb_pos > 0.85:
                score -= 1
                bear.append('價格接近布林上軌，上行空間受壓')

    vol_avg = indicators.volume_avg20
    vol_today = indicators.volume_today
    if vol_avg > 0 and vol_today > 0:
        ratio = vol_today / vol_avg
        if ratio > 1.5 and change_pct > 0:
            score += 1
            bull.append(f'放量上漲（{ratio:.1f}x 均量），買盤積極')
        elif ratio > 1.5 and change_pct < 0:
            score -= 1
            bear.append(f'放量下跌（{ratio:.1f}x 均量），賣壓沉重')

    if score >= 3:
        strength = '強烈' if score >= 5 else '偏'
        verdict = f'{strength}看漲'
    elif score <= -3:
        strength = '強烈' if score <= -5 else '偏'
        verdict = f'{strength}看跌'
    else:
        verdict = '中性觀望'

    return ScoreResult(
        score=score, verdict=verdict, bull_reasons=bull, bear_reasons=bear
    )
