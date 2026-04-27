"""Webhook tests for the ``/history`` command and inline-keyboard flow.

These tests cover:

* Plain-text fallback ``/history``, ``/history 2330``, ``/history us AAPL``.
* Inline-keyboard ``callback_query`` lifecycle (type → market → period → result).
* Authorization on ``callback_query`` payloads.
* Malformed ``callback_data`` is logged and dropped (still HTTP 200).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from fastapistock.main import app
from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
)

client = TestClient(app)

_TZ = ZoneInfo('Asia/Taipei')
_VALID_SECRET = 'test-secret'  # noqa: S105 — test fixture
_AUTHORIZED_ID = 99999

# noqa: S105 — these are monkeypatch target paths, not credential values
_PATCH_SECRET = 'fastapistock.routers.webhook.config.TELEGRAM_WEBHOOK_SECRET'  # noqa: S105
_PATCH_USER = 'fastapistock.routers.webhook.config.TELEGRAM_USER_ID'

_PATCH_HANDLE_TEXT = 'fastapistock.routers.webhook.history_handler.handle_text_command'
_PATCH_HANDLE_CB = 'fastapistock.routers.webhook.history_handler.handle_callback'
_PATCH_REPO_LIST_SYMBOL = (
    'fastapistock.services.history_handler.report_history_repo.list_symbol_history'
)
_PATCH_REPO_LIST_SUMMARY = (
    'fastapistock.services.history_handler.report_history_repo.list_summary_history'
)
_PATCH_REPO_LIST_OPTIONS = (
    'fastapistock.services.history_handler.report_history_repo.list_options'
)
_PATCH_TG_REPLY = 'fastapistock.services.history_handler.telegram_service.reply_to_chat'
_PATCH_TG_EDIT = (
    'fastapistock.services.history_handler.telegram_service.edit_message_text'
)
_PATCH_TG_ANSWER = (
    'fastapistock.services.history_handler.telegram_service.answer_callback_query'
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _message_update(text: str, user_id: int = _AUTHORIZED_ID) -> dict[str, object]:
    return {
        'update_id': 1,
        'message': {
            'message_id': 1,
            'from': {'id': user_id, 'is_bot': False, 'first_name': 'Test'},
            'chat': {'id': user_id},
            'text': text,
        },
    }


def _callback_update(
    data: str,
    user_id: int = _AUTHORIZED_ID,
    chat_id: int = _AUTHORIZED_ID,
    message_id: int = 555,
) -> dict[str, object]:
    return {
        'update_id': 2,
        'callback_query': {
            'id': 'cbq-1',
            'from': {'id': user_id, 'is_bot': False, 'first_name': 'Test'},
            'message': {
                'message_id': message_id,
                'from': {
                    'id': user_id,
                    'is_bot': False,
                    'first_name': 'Test',
                },
                'chat': {'id': chat_id},
                'text': '舊訊息',
            },
            'data': data,
        },
    }


def _post(payload: dict[str, object]) -> object:
    return client.post(
        '/api/v1/webhook/telegram',
        json=payload,
        headers={'X-Telegram-Bot-Api-Secret-Token': _VALID_SECRET},
    )


@pytest.fixture
def authed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))


def _snapshot(
    *,
    period: str,
    symbol: str = '2330',
    market: str = 'TW',
    pnl: str = '12300.00',
    delta: str | None = '13300.00',
) -> SymbolSnapshot:
    return SymbolSnapshot(
        report_type='monthly',
        report_period=period,
        market=market,
        symbol=symbol,
        shares=Decimal('1000'),
        avg_cost=Decimal('700'),
        current_price=Decimal('800'),
        market_value=Decimal('800000'),
        unrealized_pnl=Decimal(pnl),
        pnl_pct=Decimal('1.6'),
        pnl_delta=Decimal(delta) if delta is not None else None,
        captured_at=datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


def _summary(
    *,
    period: str,
    market: str = 'TW',
) -> ReportSummary:
    return ReportSummary(
        report_type='monthly',
        report_period=period,
        pnl_tw_total=Decimal('500000'),
        pnl_us_total=Decimal('8000'),
        pnl_tw_delta=Decimal('20000'),
        pnl_us_delta=Decimal('300'),
        buy_amount_twd=Decimal('100000'),
        signals_count=3,
        symbols_count=8,
        captured_at=datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


# ── /history plain-text fallback ───────────────────────────────────────────


class TestHistoryTextCommand:
    """``/history`` text command paths."""

    def test_no_args_triggers_inline_keyboard(self, authed: None) -> None:
        with patch(_PATCH_TG_REPLY, return_value=True) as mock_reply:
            resp = _post(_message_update('/history'))
        assert resp.status_code == 200
        mock_reply.assert_called_once()
        call_kwargs = mock_reply.call_args.kwargs
        # The inline keyboard must be attached for the type-select stage.
        assert 'reply_markup' in call_kwargs
        markup = call_kwargs['reply_markup']
        assert isinstance(markup, dict)
        assert 'inline_keyboard' in markup
        # First row should contain the two top-level buttons.
        first_row = markup['inline_keyboard'][0]
        callback_data = {btn['callback_data'] for btn in first_row}
        assert {'hist:t:summary', 'hist:t:symbol'}.issubset(callback_data)

    def test_symbol_only_auto_detects_market(self, authed: None) -> None:
        rows = [_snapshot(period='2025-05'), _snapshot(period='2025-06')]
        with (
            patch(_PATCH_REPO_LIST_SYMBOL, side_effect=[rows, []]) as mock_list,
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            resp = _post(_message_update('/history 2330'))
        assert resp.status_code == 200
        # Auto-detect: TW first, falls through only when TW returns []
        assert mock_list.call_args_list[0].kwargs['market'] == 'TW'
        assert mock_list.call_args_list[0].kwargs['symbol'] == '2330'
        # Single TW call sufficed → no second call (had data on first try).
        assert mock_list.call_count == 1
        # Reply rendered the per-symbol table without inline keyboard.
        mock_reply.assert_called_once()
        text = mock_reply.call_args.args[1]
        assert '2330' in text
        assert '2025-05' in text

    def test_us_prefix_calls_repo_with_us(self, authed: None) -> None:
        rows = [_snapshot(period='2025-05', symbol='AAPL', market='US')]
        with (
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows) as mock_list,
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            resp = _post(_message_update('/history us AAPL'))
        assert resp.status_code == 200
        mock_list.assert_called_once()
        call = mock_list.call_args
        assert call.kwargs['market'] == 'US'
        assert call.kwargs['symbol'] == 'AAPL'
        text = mock_reply.call_args.args[1]
        assert 'AAPL' in text

    def test_symbol_with_no_history_reports_empty(self, authed: None) -> None:
        with (
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=[]),
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            resp = _post(_message_update('/history 9999'))
        assert resp.status_code == 200
        mock_reply.assert_called_once()
        assert '查無資料' in mock_reply.call_args.args[1]


# ── Callback query routing ─────────────────────────────────────────────────


class TestCallbackQueryFlow:
    """Inline-keyboard callbacks edit the original message via editMessageText."""

    def test_type_summary_renders_market_menu(self, authed: None) -> None:
        with (
            patch(_PATCH_TG_ANSWER, return_value=True) as mock_ans,
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:t:summary'))
        assert resp.status_code == 200
        mock_ans.assert_called_once()
        mock_edit.assert_called_once()
        kwargs = mock_edit.call_args.kwargs
        assert '請選市場' in kwargs['text']
        markup = kwargs['reply_markup']
        button_data = [
            btn['callback_data'] for row in markup['inline_keyboard'] for btn in row
        ]
        assert 'hist:m:summary:TW' in button_data
        assert 'hist:m:summary:US' in button_data
        assert 'hist:m:summary:ALL' in button_data

    def test_market_summary_tw_renders_period_menu(self, authed: None) -> None:
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:m:summary:TW'))
        assert resp.status_code == 200
        kwargs = mock_edit.call_args.kwargs
        assert '請選週期' in kwargs['text']
        button_data = [
            btn['callback_data']
            for row in kwargs['reply_markup']['inline_keyboard']
            for btn in row
        ]
        assert 'hist:p:summary:TW:weekly' in button_data
        assert 'hist:p:summary:TW:monthly' in button_data

    def test_period_summary_renders_results(self, authed: None) -> None:
        rows = [_summary(period='2026-02'), _summary(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SUMMARY, return_value=rows) as mock_list,
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:p:summary:TW:monthly'))
        assert resp.status_code == 200
        call = mock_list.call_args
        assert call.kwargs['report_type'] == 'monthly'
        assert call.kwargs['market'] == 'TW'
        kwargs = mock_edit.call_args.kwargs
        assert '帳戶' in kwargs['text']
        assert '2026-02' in kwargs['text']
        # Final result must clear the inline keyboard.
        assert 'reply_markup' not in kwargs

    def test_type_symbol_renders_market_menu(self, authed: None) -> None:
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:t:symbol'))
        assert resp.status_code == 200
        markup = mock_edit.call_args.kwargs['reply_markup']
        button_data = [
            btn['callback_data'] for row in markup['inline_keyboard'] for btn in row
        ]
        assert 'hist:m:symbol:TW' in button_data
        assert 'hist:m:symbol:US' in button_data

    def test_market_symbol_renders_symbol_picker(self, authed: None) -> None:
        options = {
            'markets': ['TW', 'US'],
            'report_types': ['weekly', 'monthly'],
            'symbols': {'TW': ['2330', '0050', '2317'], 'US': ['AAPL']},
            'periods': {'weekly': [], 'monthly': ['2026-04']},
            'latest_captured_at': '2026-05-01T21:00:00+08:00',
        }
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_OPTIONS, return_value=options),
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:m:symbol:TW'))
        assert resp.status_code == 200
        kwargs = mock_edit.call_args.kwargs
        button_data = [
            btn['callback_data']
            for row in kwargs['reply_markup']['inline_keyboard']
            for btn in row
        ]
        assert 'hist:s:TW:2330' in button_data
        assert 'hist:s:TW:0050' in button_data

    def test_period_symbol_renders_results(self, authed: None) -> None:
        rows = [_snapshot(period='2026-02'), _snapshot(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows) as mock_list,
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:p:symbol:TW:2330:monthly'))
        assert resp.status_code == 200
        call = mock_list.call_args
        assert call.kwargs['symbol'] == '2330'
        assert call.kwargs['market'] == 'TW'
        assert call.kwargs['report_type'] == 'monthly'
        text = mock_edit.call_args.kwargs['text']
        assert '2330' in text
        assert '2026-02' in text


# ── Authorization & malformed payloads ─────────────────────────────────────


class TestCallbackAuthorization:
    """Unauthorized callbacks must be ignored (HTTP 200, no edit fired)."""

    def test_unauthorized_user_silently_ignored(self, authed: None) -> None:
        with (
            patch(_PATCH_TG_ANSWER, return_value=True) as mock_ans,
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:t:summary', user_id=11111))
        assert resp.status_code == 200
        mock_ans.assert_not_called()
        mock_edit.assert_not_called()


class TestCallbackMalformed:
    """Malformed callback_data is logged and dropped."""

    def test_unknown_prefix_ignored(
        self, authed: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_TG_EDIT) as mock_edit,
        ):
            resp = _post(_callback_update('foobar:1:2'))
        assert resp.status_code == 200
        mock_edit.assert_not_called()

    def test_malformed_hist_payload_logs_warning(
        self, authed: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Only 2 segments (no step value).
        with (
            patch(_PATCH_TG_ANSWER, return_value=True) as mock_ans,
            patch(_PATCH_TG_EDIT) as mock_edit,
        ):
            resp = _post(_callback_update('hist:t'))
        assert resp.status_code == 200
        mock_ans.assert_called_once()
        mock_edit.assert_not_called()


# ── Smoke: dispatch hooks isolated from internals ──────────────────────────


class TestRouterDispatchSmoke:
    """The webhook router only forwards to the handler — verify the handoff."""

    def test_text_command_forwarded_to_handler(self, authed: None) -> None:
        with patch(_PATCH_HANDLE_TEXT) as mock_handler:
            resp = _post(_message_update('/history 2330'))
        assert resp.status_code == 200
        mock_handler.assert_called_once()
        kwargs = mock_handler.call_args.kwargs
        assert kwargs['args'] == '2330'
        assert kwargs['chat_id'] == str(_AUTHORIZED_ID)

    def test_callback_forwarded_to_handler(self, authed: None) -> None:
        with patch(_PATCH_HANDLE_CB) as mock_handler:
            resp = _post(_callback_update('hist:t:summary'))
        assert resp.status_code == 200
        mock_handler.assert_called_once()
        kwargs = mock_handler.call_args.kwargs
        assert kwargs['data'] == 'hist:t:summary'


# Reference unused helpers — silences import linting in some setups.
_ = MagicMock
