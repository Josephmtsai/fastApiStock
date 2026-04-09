"""Tests for the US stock repository."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.repositories.us_stock_repo import fetch_us_stock
from fastapistock.schemas.stock import RichStockData


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


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_returns_rich_stock_data(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_hist(60)
    mock_ticker.info = {'longName': 'Apple Inc.'}
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
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_hist(60)
    mock_ticker.info = {}
    mock_ticker_cls.return_value = mock_ticker

    fetch_us_stock('AAPL')

    # yf.Ticker should be called with the raw symbol, no .TW appended
    mock_ticker_cls.assert_called_once_with('AAPL')


@patch('fastapistock.repositories.us_stock_repo.yf.Ticker')
@patch('fastapistock.repositories.us_stock_repo.time.sleep')
def test_price_and_change_calculated(
    mock_sleep: MagicMock, mock_ticker_cls: MagicMock
) -> None:
    hist = _make_hist(60, price=150.0)
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = hist
    mock_ticker.info = {}
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_us_stock('TSLA')

    assert result.price == pytest.approx(150.0, rel=0.01)
    assert result.prev_close == pytest.approx(150.0, rel=0.01)
    assert result.change == pytest.approx(0.0, abs=0.01)
