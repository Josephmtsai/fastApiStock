"""Integration tests for POST /api/v1/webhook/telegram."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from fastapistock.main import app

_client = TestClient(app)

_VALID_SECRET = 'test-secret'  # noqa: S105 — test fixture value, not a real credential
_AUTHORIZED_ID = 99999

# noqa: S105 — these are monkeypatch target paths, not credential values
_PATCH_SECRET = 'fastapistock.routers.webhook.config.TELEGRAM_WEBHOOK_SECRET'  # noqa: S105
_PATCH_USER = 'fastapistock.routers.webhook.config.TELEGRAM_USER_ID'
_PATCH_REPLY = 'fastapistock.routers.webhook.reply_to_chat'
_PATCH_ACHIEVEMENT = 'fastapistock.routers.webhook._handle_q'
_PATCH_US = 'fastapistock.routers.webhook._handle_us'
_PATCH_TW = 'fastapistock.routers.webhook._handle_tw'


def _make_update(text: str, user_id: int = _AUTHORIZED_ID) -> dict[str, object]:
    return {
        'update_id': 1,
        'message': {
            'message_id': 1,
            'from': {'id': user_id, 'is_bot': False, 'first_name': 'Test'},
            'chat': {'id': user_id},
            'text': text,
        },
    }


def _post(payload: dict[str, object], secret: str = _VALID_SECRET) -> Response:
    return _client.post(
        '/api/v1/webhook/telegram',
        json=payload,
        headers={'X-Telegram-Bot-Api-Secret-Token': secret},
    )


# ---------------------------------------------------------------------------
# Secret token validation
# ---------------------------------------------------------------------------


def test_missing_secret_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    resp = _client.post(
        '/api/v1/webhook/telegram',
        json=_make_update('/help'),
        # no secret header
    )
    assert resp.status_code == 403


def test_wrong_secret_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    resp = _post(_make_update('/help'), secret='wrong-secret')  # noqa: S106
    assert resp.status_code == 403


def test_correct_secret_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))
    with patch(_PATCH_REPLY, return_value=True):
        resp = _post(_make_update('/help'))
    assert resp.status_code == 200
    assert resp.json()['status'] == 'success'


# ---------------------------------------------------------------------------
# Unauthorized user ID
# ---------------------------------------------------------------------------


def test_unauthorized_user_silently_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))
    with patch(_PATCH_REPLY) as mock_reply:
        resp = _post(_make_update('/q', user_id=11111))
    assert resp.status_code == 200
    mock_reply.assert_not_called()


# ---------------------------------------------------------------------------
# /q command
# ---------------------------------------------------------------------------


def test_q_command_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))

    with (
        patch(_PATCH_ACHIEVEMENT, return_value='達成率 50%') as mock_q,
        patch(_PATCH_REPLY, return_value=True) as mock_reply,
    ):
        resp = _post(_make_update('/q'))

    assert resp.status_code == 200
    mock_q.assert_called_once()
    mock_reply.assert_called_once_with(str(_AUTHORIZED_ID), '達成率 50%')


# ---------------------------------------------------------------------------
# /us command
# ---------------------------------------------------------------------------


def test_us_with_symbols_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))

    with (
        patch(_PATCH_US, return_value='AAPL price') as mock_us,
        patch(_PATCH_REPLY, return_value=True),
    ):
        resp = _post(_make_update('/us AAPL,TSLA'))

    assert resp.status_code == 200
    mock_us.assert_called_once_with('AAPL,TSLA')


def test_us_without_args_returns_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))

    _usage = '用法：/us AAPL,TSLA\n請提供至少一個美股代號（以逗號分隔）'
    with (
        patch(_PATCH_US, return_value=_usage) as mock_us,
        patch(_PATCH_REPLY, return_value=True) as mock_reply,
    ):
        resp = _post(_make_update('/us'))

    assert resp.status_code == 200
    mock_us.assert_called_once_with('')
    reply_text = mock_reply.call_args[0][1]
    assert '用法' in reply_text


# ---------------------------------------------------------------------------
# /tw command
# ---------------------------------------------------------------------------


def test_tw_with_codes_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))

    with (
        patch(_PATCH_TW, return_value='2330 price') as mock_tw,
        patch(_PATCH_REPLY, return_value=True),
    ):
        resp = _post(_make_update('/tw 0050,2330'))

    assert resp.status_code == 200
    mock_tw.assert_called_once_with('0050,2330')


# ---------------------------------------------------------------------------
# /help command
# ---------------------------------------------------------------------------


def test_help_command_replies_with_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))

    with patch(_PATCH_REPLY, return_value=True) as mock_reply:
        resp = _post(_make_update('/help'))

    assert resp.status_code == 200
    reply_text = mock_reply.call_args[0][1]
    assert '/q' in reply_text
    assert '/us' in reply_text
    assert '/tw' in reply_text
    assert '/help' in reply_text


# ---------------------------------------------------------------------------
# Unrecognized command — silently ignored
# ---------------------------------------------------------------------------


def test_unknown_command_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))

    with patch(_PATCH_REPLY) as mock_reply:
        resp = _post(_make_update('/unknown'))

    assert resp.status_code == 200
    mock_reply.assert_not_called()


# ---------------------------------------------------------------------------
# Non-text message — silently ignored
# ---------------------------------------------------------------------------


def test_non_text_message_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))

    payload = {
        'update_id': 2,
        'message': {
            'message_id': 2,
            'from': {'id': _AUTHORIZED_ID, 'is_bot': False, 'first_name': 'Test'},
            'chat': {'id': _AUTHORIZED_ID},
            # no 'text' key → treated as None
        },
    }
    with patch(_PATCH_REPLY) as mock_reply:
        resp = _post(payload)

    assert resp.status_code == 200
    mock_reply.assert_not_called()
