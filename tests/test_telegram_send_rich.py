"""Tests for send_rich_stock_message error paths and _format_rich_block edge cases."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import httpx

from fastapistock.schemas.stock import RichStockData
from fastapistock.services.telegram_service import (
    format_rich_stock_message,
    send_rich_stock_message,
)

_TZ = ZoneInfo('Asia/Taipei')
_NOW = datetime(2026, 4, 9, 10, 0, tzinfo=_TZ)

_STOCK = RichStockData(
    symbol='0050',
    display_name='元大台灣50',
    market='TW',
    price=185.0,
    prev_close=182.0,
    change=3.0,
    change_pct=1.65,
    rsi=65.0,
    macd=0.5,
    macd_signal=0.3,
    macd_hist=0.2,
    ma20=180.0,
    ma50=175.0,
    bb_upper=190.0,
    bb_mid=183.0,
    bb_lower=176.0,
    volume=10_000_000,
    volume_avg20=8_000_000,
    week52_high=195.0,
    week52_low=155.0,
)

_STOCK_AT_BB_UPPER = RichStockData(
    symbol='2330',
    display_name='台積電',
    market='TW',
    price=192.0,
    prev_close=190.0,
    change=2.0,
    change_pct=1.05,
    ma20=183.0,
    bb_upper=192.0,
    bb_mid=183.0,
    bb_lower=174.0,
    volume=5_000_000,
    volume_avg20=4_000_000,
)

_STOCK_AT_BB_LOWER = RichStockData(
    symbol='2330',
    display_name='台積電',
    market='TW',
    price=174.0,
    prev_close=176.0,
    change=-2.0,
    change_pct=-1.14,
    ma20=183.0,
    bb_upper=192.0,
    bb_mid=183.0,
    bb_lower=174.0,
    volume=5_000_000,
    volume_avg20=4_000_000,
)


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', '')
def test_send_rich_returns_false_when_no_token() -> None:
    result = send_rich_stock_message('123', [_STOCK], market='TW')
    assert result is False


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
@patch('fastapistock.services.telegram_service.httpx.post')
def test_send_rich_returns_true_on_success(mock_post: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp
    result = send_rich_stock_message('123', [_STOCK], market='TW')
    assert result is True


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
@patch('fastapistock.services.telegram_service.httpx.post')
def test_send_rich_returns_false_on_http_error(mock_post: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = 'Bad Request'
    mock_post.return_value = mock_resp
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        'error', request=MagicMock(), response=mock_resp
    )
    result = send_rich_stock_message('123', [_STOCK], market='TW')
    assert result is False


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
@patch('fastapistock.services.telegram_service.httpx.post')
def test_send_rich_returns_false_on_request_error(mock_post: MagicMock) -> None:
    mock_post.side_effect = httpx.RequestError('timeout', request=MagicMock())
    result = send_rich_stock_message('123', [_STOCK], market='TW')
    assert result is False


def test_format_rich_block_bb_upper_tag() -> None:
    # Bollinger band display removed (Track 1); score reasons may still reference BB
    msg = format_rich_stock_message([_STOCK_AT_BB_UPPER], 'TW', _NOW)
    assert '布林' not in msg or '觸上軌' not in msg  # display line gone


def test_format_rich_block_bb_lower_tag() -> None:
    # Bollinger band display removed (Track 1); score reasons may still reference BB
    msg = format_rich_stock_message([_STOCK_AT_BB_LOWER], 'TW', _NOW)
    assert '布林' not in msg or '觸下軌' not in msg  # display line gone


def test_format_rich_block_rsi_overbought() -> None:
    stock = RichStockData(
        symbol='TEST',
        display_name='Test',
        market='TW',
        price=100.0,
        prev_close=99.0,
        change=1.0,
        change_pct=1.0,
        ma20=98.0,
        rsi=75.0,
        volume=1_000_000,
        volume_avg20=800_000,
    )
    msg = format_rich_stock_message([stock], 'TW', _NOW)
    assert '超買' in msg


def test_format_rich_block_rsi_oversold() -> None:
    stock = RichStockData(
        symbol='TEST',
        display_name='Test',
        market='TW',
        price=100.0,
        prev_close=99.0,
        change=1.0,
        change_pct=1.0,
        ma20=98.0,
        rsi=25.0,
        volume=1_000_000,
        volume_avg20=800_000,
    )
    msg = format_rich_stock_message([stock], 'TW', _NOW)
    assert '超賣' in msg
