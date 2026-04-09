"""Tests for the upgraded TW stock Telegram push endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from fastapistock.main import app
from fastapistock.schemas.stock import RichStockData

_client = TestClient(app)

_RICH_STOCK = RichStockData(
    symbol='0050',
    display_name='元大台灣50',
    market='TW',
    price=195.5,
    prev_close=193.2,
    change=2.3,
    change_pct=1.19,
    ma20=190.0,
    volume=5_000_000,
    volume_avg20=4_000_000,
)


@patch('fastapistock.routers.telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.telegram.get_rich_tw_stocks', return_value=[_RICH_STOCK])
def test_valid_code_returns_success(mock_get: MagicMock, mock_send: MagicMock) -> None:
    resp = _client.get('/api/v1/tgMessage/123456?stock=0050')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'success'
    mock_get.assert_called_once_with(['0050'])
    mock_send.assert_called_once_with('123456', [_RICH_STOCK], market='TW')


@patch('fastapistock.routers.telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.telegram.get_rich_tw_stocks', return_value=[_RICH_STOCK])
def test_non_numeric_code_filtered_returns_error(
    mock_get: MagicMock, mock_send: MagicMock
) -> None:
    resp = _client.get('/api/v1/tgMessage/123456?stock=abc,xyz')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'error'
    mock_get.assert_not_called()


@patch('fastapistock.routers.telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.telegram.get_rich_tw_stocks', return_value=[_RICH_STOCK])
def test_empty_stock_param_returns_error(
    mock_get: MagicMock, mock_send: MagicMock
) -> None:
    resp = _client.get('/api/v1/tgMessage/123456?stock=')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'error'
    mock_get.assert_not_called()


@patch('fastapistock.routers.telegram.send_rich_stock_message', return_value=False)
@patch('fastapistock.routers.telegram.get_rich_tw_stocks', return_value=[_RICH_STOCK])
def test_telegram_send_failure_returns_error(
    mock_get: MagicMock, mock_send: MagicMock
) -> None:
    resp = _client.get('/api/v1/tgMessage/123456?stock=0050')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'error'


@patch('fastapistock.routers.telegram.send_rich_stock_message', return_value=True)
@patch('fastapistock.routers.telegram.get_rich_tw_stocks', return_value=[_RICH_STOCK])
def test_market_tw_passed_to_send(mock_get: MagicMock, mock_send: MagicMock) -> None:
    _client.get('/api/v1/tgMessage/999?stock=2330')
    _, kwargs = mock_send.call_args
    assert kwargs.get('market') == 'TW'
