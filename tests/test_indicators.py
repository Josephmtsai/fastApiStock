"""Tests for the technical indicators service."""

import math
from datetime import date

import pandas as pd
import pytest

from fastapistock.services.indicators import (
    IndicatorResult,
    calculate,
    score_stock,
)


def _make_hist(n: int, price: float = 100.0, volume: int = 1_000_000) -> pd.DataFrame:
    """Return a synthetic OHLCV DataFrame with *n* rows at a constant price."""
    return pd.DataFrame(
        {
            'Open': [price] * n,
            'High': [price * 1.01] * n,
            'Low': [price * 0.99] * n,
            'Close': [price] * n,
            'Volume': [volume] * n,
        },
        index=pd.date_range(start=date(2025, 1, 1), periods=n, freq='B'),
    )


def _make_trend_hist(n: int, start: float = 80.0, end: float = 120.0) -> pd.DataFrame:
    """Return a DataFrame with linearly increasing close prices."""
    prices = [start + (end - start) * i / (n - 1) for i in range(n)]
    return pd.DataFrame(
        {
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
            'Close': prices,
            'Volume': [1_000_000] * n,
        },
        index=pd.date_range(start=date(2025, 1, 1), periods=n, freq='B'),
    )


class TestCalculate:
    def test_returns_indicator_result_type(self) -> None:
        hist = _make_hist(60)
        result = calculate(hist)
        assert isinstance(result, IndicatorResult)

    def test_ma20_present_with_60_rows(self) -> None:
        hist = _make_hist(60)
        result = calculate(hist)
        assert result.ma20 is not None
        assert not math.isnan(result.ma20)

    def test_ma50_present_with_60_rows(self) -> None:
        hist = _make_hist(60)
        result = calculate(hist)
        assert result.ma50 is not None

    def test_bb_upper_none_when_fewer_than_20_rows(self) -> None:
        hist = _make_hist(15)
        result = calculate(hist)
        assert result.bb_upper is None
        assert result.bb_mid is None
        assert result.bb_lower is None

    def test_rsi_present_with_60_rows(self) -> None:
        hist = _make_hist(60)
        result = calculate(hist)
        assert result.rsi is not None
        assert 0.0 <= result.rsi <= 100.0

    def test_macd_present_with_60_rows(self) -> None:
        hist = _make_hist(60)
        result = calculate(hist)
        assert result.macd is not None
        assert result.macd_signal is not None
        assert result.macd_hist is not None

    def test_macd_none_when_history_short(self) -> None:
        hist = _make_hist(20)
        result = calculate(hist)
        assert result.macd is None

    def test_volume_today_matches_last_row(self) -> None:
        hist = _make_hist(60, volume=500_000)
        result = calculate(hist)
        assert result.volume_today == 500_000

    def test_week52_high_is_max_high(self) -> None:
        hist = _make_hist(60, price=100.0)
        result = calculate(hist)
        assert result.week52_high is not None
        assert result.week52_high == pytest.approx(101.0, rel=0.01)

    def test_week52_low_is_min_low(self) -> None:
        hist = _make_hist(60, price=100.0)
        result = calculate(hist)
        assert result.week52_low is not None
        assert result.week52_low == pytest.approx(99.0, rel=0.01)


class TestScoreStock:
    def _ind(self, **kwargs: object) -> IndicatorResult:
        defaults: dict[str, object] = {
            'rsi': None,
            'macd': None,
            'macd_signal': None,
            'macd_hist': None,
            'ma20': None,
            'ma50': None,
            'bb_upper': None,
            'bb_mid': None,
            'bb_lower': None,
            'volume_today': 0,
            'volume_avg20': 0,
            'week52_high': None,
            'week52_low': None,
        }
        defaults.update(kwargs)
        return IndicatorResult(**defaults)  # type: ignore[arg-type]

    def test_rsi_below_30_adds_2(self) -> None:
        ind = self._ind(rsi=25.0)
        result = score_stock(100.0, 0.0, ind)
        assert result.score >= 2
        assert any('RSI' in r for r in result.bull_reasons)

    def test_rsi_above_70_subtracts_2(self) -> None:
        ind = self._ind(rsi=75.0)
        result = score_stock(100.0, 0.0, ind)
        assert result.score <= -2
        assert any('RSI' in r for r in result.bear_reasons)

    def test_macd_golden_cross_above_zero_adds_2(self) -> None:
        ind = self._ind(macd=0.5, macd_hist=0.1, macd_signal=0.4)
        result = score_stock(100.0, 0.0, ind)
        assert result.score >= 2
        assert any('金叉' in r for r in result.bull_reasons)

    def test_macd_death_cross_below_zero_subtracts_2(self) -> None:
        ind = self._ind(macd=-0.5, macd_hist=-0.1, macd_signal=-0.4)
        result = score_stock(100.0, 0.0, ind)
        assert result.score <= -2

    def test_bullish_score_gte_3_gives_bullish_verdict(self) -> None:
        ind = self._ind(rsi=25.0, macd=0.5, macd_hist=0.1, macd_signal=0.4, ma20=90.0)
        result = score_stock(100.0, 1.0, ind)
        assert result.score >= 3
        assert '看漲' in result.verdict

    def test_bearish_score_lte_minus3_gives_bearish_verdict(self) -> None:
        ind = self._ind(
            rsi=75.0, macd=-0.5, macd_hist=-0.1, macd_signal=-0.4, ma20=110.0
        )
        result = score_stock(100.0, -1.0, ind)
        assert result.score <= -3
        assert '看跌' in result.verdict

    def test_neutral_score_gives_neutral_verdict(self) -> None:
        ind = self._ind()
        result = score_stock(100.0, 0.0, ind)
        assert result.verdict == '中性觀望'
