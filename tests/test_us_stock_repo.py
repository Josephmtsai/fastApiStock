"""Tests for the US stock repository."""

from datetime import UTC, date
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.repositories.us_stock_repo import (
    _fetch_premarket_price,
    fetch_us_stock,
)
from fastapistock.schemas.stock import RichStockData

_ET = ZoneInfo('America/New_York')


def _make_hist(n: int = 60, price: float = 150.0) -> pd.DataFrame:
    prices = [price] * n
    return pd.DataFrame(
        {
            'Open': prices,
            'High': [p * 1.01 for p in prices],
            'Low': [p * 0.99 for p in prices],
            'Close': prices,
            'Volume': [50_000_000] * n,
        },
        index=pd.date_range(start=date(2025, 1, 1), periods=n, freq='B'),
    )


def _make_premarket_hist(close: float = 185.5) -> pd.DataFrame:
    """Build a 1-minute DataFrame with one row in ET pre-market (04:30 ET).

    2025-01-02 is in Eastern Standard Time (UTC-5).
    04:30 ET = 09:30 UTC.
    """
    idx = pd.DatetimeIndex(
        ['2025-01-02 09:30:00'],
        tz=UTC,
    ).tz_convert(_ET)
    return pd.DataFrame(
        {
            'Open': [close],
            'High': [close],
            'Low': [close],
            'Close': [close],
            'Volume': [100_000],
        },
        index=idx,
    )


def _make_ticker_mock(
    daily_hist: pd.DataFrame,
    premarket_hist: pd.DataFrame | None = None,
    info: dict | None = None,
) -> MagicMock:
    """Return a Ticker mock whose .history() returns correct data per call."""
    mock = MagicMock()
    mock.info = info or {}
    empty = pd.DataFrame()

    def _history_side_effect(**kwargs: object) -> pd.DataFrame:
        if kwargs.get('prepost') is True:
            return premarket_hist if premarket_hist is not None else empty
        return daily_hist

    mock.history.side_effect = _history_side_effect
    return mock


# ---------------------------------------------------------------------------
# _fetch_premarket_price unit tests
# ---------------------------------------------------------------------------


def test_fetch_premarket_price_returns_value_during_premarket() -> None:
    ticker = MagicMock()
    ticker.history.return_value = _make_premarket_hist(185.5)
    result = _fetch_premarket_price(ticker)
    assert result == pytest.approx(185.5, rel=0.001)


def test_fetch_premarket_price_returns_none_on_empty_hist() -> None:
    ticker = MagicMock()
    ticker.history.return_value = pd.DataFrame()
    assert _fetch_premarket_price(ticker) is None


def test_fetch_premarket_price_returns_none_when_no_premarket_rows() -> None:
    """Rows outside 04:00–09:30 ET should yield None."""
    idx = pd.DatetimeIndex(
        ['2025-01-02 15:00:00'],
        tz=UTC,
    ).tz_convert(_ET)
    df = pd.DataFrame(
        {
            'Open': [150.0],
            'High': [150.0],
            'Low': [150.0],
            'Close': [150.0],
            'Volume': [0],
        },
        index=idx,
    )
    ticker = MagicMock()
    ticker.history.return_value = df
    assert _fetch_premarket_price(ticker) is None


def test_fetch_premarket_price_returns_none_on_exception() -> None:
    ticker = MagicMock()
    ticker.history.side_effect = RuntimeError('network error')
    assert _fetch_premarket_price(ticker) is None


def test_fetch_premarket_price_rounds_to_two_decimals() -> None:
    ticker = MagicMock()
    ticker.history.return_value = _make_premarket_hist(185.123456)
    result = _fetch_premarket_price(ticker)
    assert result == 185.12


# ---------------------------------------------------------------------------
# fetch_us_stock integration tests
# ---------------------------------------------------------------------------


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_returns_rich_stock_data(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = _make_ticker_mock(
        daily_hist=_make_hist(60),
        premarket_hist=_make_premarket_hist(185.5),
        info={'longName': 'Apple Inc.'},
    )
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('AAPL')

    assert isinstance(result, RichStockData)
    assert result.symbol == 'AAPL'
    assert result.market == 'US'
    assert result.display_name == 'Apple Inc.'


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_empty_history_raises_stock_not_found(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    mock_ticker.info = {}
    mock_ticker_cls.return_value = mock_ticker

    with pytest.raises(StockNotFoundError):
        fetch_us_stock('INVALID')


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_symbol_used_without_tw_suffix(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = _make_ticker_mock(daily_hist=_make_hist(60))
    mock_ticker_cls.return_value = mock_ticker

    fetch_us_stock('AAPL')

    mock_ticker_cls.assert_called_once_with('AAPL')


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_price_and_change_calculated(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    hist = _make_hist(60, price=150.0)
    mock_ticker = _make_ticker_mock(daily_hist=hist)
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('TSLA')

    assert result.price == pytest.approx(150.0, rel=0.01)
    assert result.prev_close == pytest.approx(150.0, rel=0.01)
    assert result.change == pytest.approx(0.0, abs=0.01)


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_premarket_price_populated_during_premarket(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = _make_ticker_mock(
        daily_hist=_make_hist(60),
        premarket_hist=_make_premarket_hist(188.0),
    )
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('AAPL')

    assert result.premarket_price == pytest.approx(188.0, rel=0.001)


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_premarket_price_none_outside_premarket(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = _make_ticker_mock(
        daily_hist=_make_hist(60),
        premarket_hist=None,
    )
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('AAPL')

    assert result.premarket_price is None
