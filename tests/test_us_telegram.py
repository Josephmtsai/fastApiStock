"""Tests for the US stock Telegram push endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from fastapistock.main import app
from fastapistock.schemas.stock import RichStockData

_client = TestClient(app)

_US_STOCK = RichStockData(
    symbol='AAPL',
    display_name='Apple Inc.',
    market='US',
    price=195.5,
    prev_close=193.2,
    change=2.3,
    change_pct=1.19,
    ma20=190.0,
    volume=80_000_000,
    volume_avg20=70_000_000,
)


@patch('fastapistock.routers.us_telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.us_telegram.get_us_stocks', return_value=[_US_STOCK])
def test_valid_ticker_returns_success(
    mock_get: MagicMock, mock_send: MagicMock
) -> None:
    resp = _client.get('/api/v1/usMessage/123456?stock=AAPL')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'success'
    mock_get.assert_called_once_with(['AAPL'])


@patch('fastapistock.routers.us_telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.us_telegram.get_us_stocks', return_value=[_US_STOCK])
def test_lowercase_ticker_uppercased(mock_get: MagicMock, mock_send: MagicMock) -> None:
    resp = _client.get('/api/v1/usMessage/123456?stock=aapl')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'success'
    mock_get.assert_called_once_with(['AAPL'])


@patch('fastapistock.routers.us_telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.us_telegram.get_us_stocks', return_value=[_US_STOCK])
def test_ticker_with_digit_filtered_returns_error(
    mock_get: MagicMock, mock_send: MagicMock
) -> None:
    resp = _client.get('/api/v1/usMessage/123456?stock=AAP1')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'error'
    mock_get.assert_not_called()


@patch('fastapistock.routers.us_telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.us_telegram.get_us_stocks', return_value=[_US_STOCK])
def test_empty_stock_param_returns_error(
    mock_get: MagicMock, mock_send: MagicMock
) -> None:
    resp = _client.get('/api/v1/usMessage/123456?stock=')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'error'
    mock_get.assert_not_called()


@patch('fastapistock.routers.us_telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.us_telegram.get_us_stocks', return_value=[_US_STOCK])
def test_market_us_passed_to_send(mock_get: MagicMock, mock_send: MagicMock) -> None:
    _client.get('/api/v1/usMessage/999?stock=TSLA')
    _, kwargs = mock_send.call_args
    assert kwargs.get('market') == 'US'


@patch('fastapistock.routers.us_telegram.send_rich_stock_message', return_value=False)
@patch('fastapistock.routers.us_telegram.get_us_stocks', return_value=[_US_STOCK])
def test_telegram_failure_returns_error(
    mock_get: MagicMock, mock_send: MagicMock
) -> None:
    resp = _client.get('/api/v1/usMessage/123456?stock=NVDA')
    assert resp.json()['status'] == 'error'
