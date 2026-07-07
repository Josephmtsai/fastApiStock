"""Unit tests for telegram_service.send_photo (spec-018 T3, E6/E12).

All HTTP traffic is mocked; no real Telegram request is made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from fastapistock.services.telegram_service import send_photo

_PNG = b'\x89PNG\r\n\x1a\nfakepayload'


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', '')
def test_returns_false_when_no_token() -> None:
    # E12: missing token short-circuits without any HTTP call.
    assert send_photo(123, _PNG) is False


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
@patch('fastapistock.services.telegram_service.httpx.post')
def test_success_sends_multipart_payload(mock_post: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    assert send_photo(123, _PNG, caption='2330 (TW) monthly') is True

    args, kwargs = mock_post.call_args
    assert args[0].endswith('/sendPhoto')
    assert kwargs['data'] == {'chat_id': 123, 'caption': '2330 (TW) monthly'}
    assert kwargs['files'] == {'photo': ('chart.png', _PNG, 'image/png')}
    assert kwargs['timeout'] == 10


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
@patch('fastapistock.services.telegram_service.httpx.post')
def test_caption_omitted_when_none(mock_post: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    assert send_photo('456', _PNG) is True
    assert 'caption' not in mock_post.call_args.kwargs['data']


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
@patch('fastapistock.services.telegram_service.httpx.post')
def test_returns_false_on_http_status_error(mock_post: MagicMock) -> None:
    # E6: Telegram-side rejection is logged and swallowed.
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = 'Bad Request'
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        'error', request=MagicMock(), response=mock_resp
    )
    mock_post.return_value = mock_resp
    assert send_photo(123, _PNG) is False


@patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
@patch('fastapistock.services.telegram_service.httpx.post')
def test_returns_false_on_request_error(mock_post: MagicMock) -> None:
    mock_post.side_effect = httpx.RequestError('timeout', request=MagicMock())
    assert send_photo(123, _PNG) is False
