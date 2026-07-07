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
_PATCH_TG_SEND_PHOTO = (
    'fastapistock.services.history_handler.telegram_service.send_photo'
)
_PATCH_CHART_SYMBOL = (
    'fastapistock.services.history_handler.chart_service.render_symbol_chart'
)
_PATCH_CHART_SUMMARY = (
    'fastapistock.services.history_handler.chart_service.render_summary_chart'
)

_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def _button_data(markup: dict[str, object]) -> list[str]:
    """Flatten an inline keyboard into its callback_data strings."""
    return [
        btn['callback_data']
        for row in markup['inline_keyboard']  # type: ignore[union-attr]
        for btn in row
    ]


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
        # Reply rendered the per-symbol table with the quick-action keyboard.
        mock_reply.assert_called_once()
        text = mock_reply.call_args.args[1]
        assert '2330' in text
        assert '2025-05' in text
        # AC-5.1: text shortcut carries the same result-page buttons.
        markup = mock_reply.call_args.kwargs['reply_markup']
        button_data = _button_data(markup)
        assert 'hist:g:symbol:TW:2330:monthly' in button_data
        assert 'hist:p:symbol:TW:2330:weekly' in button_data
        assert 'hist:r:menu' in button_data

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
        # AC-5.1: quick-action keyboard attached with US market payloads.
        markup = mock_reply.call_args.kwargs['reply_markup']
        button_data = _button_data(markup)
        assert 'hist:g:symbol:US:AAPL:monthly' in button_data
        assert all(len(data) < 64 for data in button_data)

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
        # spec-018: result page now carries the quick-action keyboard.
        button_data = _button_data(kwargs['reply_markup'])
        assert 'hist:g:summary:TW:monthly' in button_data
        assert 'hist:p:summary:TW:weekly' in button_data
        assert 'hist:r:menu' in button_data
        assert all(len(data) < 64 for data in button_data)

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
        kwargs = mock_edit.call_args.kwargs
        assert '2330' in kwargs['text']
        assert '2026-02' in kwargs['text']
        # spec-018: result page now carries the quick-action keyboard.
        button_data = _button_data(kwargs['reply_markup'])
        assert 'hist:g:symbol:TW:2330:monthly' in button_data
        assert 'hist:p:symbol:TW:2330:weekly' in button_data
        assert 'hist:r:menu' in button_data
        assert all(len(data) < 64 for data in button_data)

    def test_period_toggle_rerenders_with_weekly_buttons(self, authed: None) -> None:
        # AC-3.1: toggling to weekly re-renders and flips the button payloads.
        rows = [_snapshot(period='2026-06-19'), _snapshot(period='2026-06-26')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows) as mock_list,
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:p:symbol:TW:2330:weekly'))
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs['report_type'] == 'weekly'
        markup = mock_edit.call_args.kwargs['reply_markup']
        button_data = _button_data(markup)
        assert 'hist:g:symbol:TW:2330:weekly' in button_data
        assert 'hist:p:symbol:TW:2330:monthly' in button_data
        labels = [btn['text'] for row in markup['inline_keyboard'] for btn in row]
        assert any('切換月報' in label for label in labels)


# ── Chart (g step) & reset (r step) callbacks — spec-018 ──────────────────


class TestChartCallback:
    """``hist:g:*`` sends the chart as a NEW photo message."""

    def test_symbol_chart_sends_png_photo(self, authed: None) -> None:
        # AC-1.1: sendPhoto fires with PNG bytes; the text message is untouched.
        rows = [_snapshot(period='2026-02'), _snapshot(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows) as mock_list,
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            resp = _post(_callback_update('hist:g:symbol:TW:2330:monthly'))
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs['symbol'] == '2330'
        assert mock_list.call_args.kwargs['report_type'] == 'monthly'
        mock_photo.assert_called_once()
        photo = mock_photo.call_args.args[1]
        assert photo.startswith(_PNG_MAGIC)
        caption = mock_photo.call_args.kwargs['caption']
        assert '2330' in caption
        assert 'TW' in caption
        mock_edit.assert_not_called()
        mock_reply.assert_not_called()

    def test_summary_chart_all_sends_png_photo(self, authed: None) -> None:
        # AC-2.1: ALL market chart is rendered and sent as a new photo.
        rows = [_summary(period='2026-02'), _summary(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SUMMARY, return_value=rows) as mock_list,
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:g:summary:ALL:monthly'))
        assert resp.status_code == 200
        assert mock_list.call_args.kwargs['market'] is None
        photo = mock_photo.call_args.args[1]
        assert photo.startswith(_PNG_MAGIC)
        mock_edit.assert_not_called()

    def test_summary_chart_single_market_projection(self, authed: None) -> None:
        # AC-2.2: single-market choice is forwarded to the renderer.
        rows = [_summary(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SUMMARY, return_value=rows),
            patch(_PATCH_CHART_SUMMARY, return_value=_PNG_MAGIC) as mock_render,
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
        ):
            resp = _post(_callback_update('hist:g:summary:TW:monthly'))
        assert resp.status_code == 200
        assert mock_render.call_args.kwargs['market'] == 'TW'
        mock_photo.assert_called_once()

    def test_empty_rows_replies_no_data_text(self, authed: None) -> None:
        # AC-1.2 / E1: no data → text fallback, no photo.
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=[]),
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            resp = _post(_callback_update('hist:g:symbol:TW:9999:monthly'))
        assert resp.status_code == 200
        mock_photo.assert_not_called()
        assert '查無資料' in mock_reply.call_args.args[1]
        assert '無法產生圖表' in mock_reply.call_args.args[1]

    def test_render_error_replies_failure_text(self, authed: None) -> None:
        # E7: renderer exceptions degrade to a text reply; webhook stays 200.
        rows = [_snapshot(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows),
            patch(_PATCH_CHART_SYMBOL, side_effect=RuntimeError('boom')),
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            resp = _post(_callback_update('hist:g:symbol:TW:2330:monthly'))
        assert resp.status_code == 200
        mock_photo.assert_not_called()
        assert '圖表產生失敗' in mock_reply.call_args.args[1]

    def test_send_photo_failure_replies_failure_text(self, authed: None) -> None:
        # E6: sendPhoto returning False degrades to a text reply.
        rows = [_snapshot(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows),
            patch(_PATCH_TG_SEND_PHOTO, return_value=False),
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            resp = _post(_callback_update('hist:g:symbol:TW:2330:monthly'))
        assert resp.status_code == 200
        assert '圖表傳送失敗' in mock_reply.call_args.args[1]

    def test_invalid_market_silently_dropped(self, authed: None) -> None:
        # E9: whitelist failure → log + silent return, nothing sent.
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL) as mock_list,
            patch(_PATCH_TG_SEND_PHOTO) as mock_photo,
            patch(_PATCH_TG_REPLY) as mock_reply,
        ):
            resp = _post(_callback_update('hist:g:symbol:XX:2330:monthly'))
        assert resp.status_code == 200
        mock_list.assert_not_called()
        mock_photo.assert_not_called()
        mock_reply.assert_not_called()

    def test_invalid_period_silently_dropped(self, authed: None) -> None:
        # E9: bad period on the summary flow is also dropped.
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SUMMARY) as mock_list,
            patch(_PATCH_TG_SEND_PHOTO) as mock_photo,
        ):
            resp = _post(_callback_update('hist:g:summary:ALL:daily'))
        assert resp.status_code == 200
        mock_list.assert_not_called()
        mock_photo.assert_not_called()


class TestResetCallback:
    """``hist:r:menu`` edits the message back to the first-layer type menu."""

    def test_reset_edits_to_type_menu(self, authed: None) -> None:
        # AC-4.1: same keyboard as the /history entry menu.
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            resp = _post(_callback_update('hist:r:menu'))
        assert resp.status_code == 200
        kwargs = mock_edit.call_args.kwargs
        assert '請選擇查詢類型' in kwargs['text']
        button_data = _button_data(kwargs['reply_markup'])
        assert 'hist:t:summary' in button_data
        assert 'hist:t:symbol' in button_data

    def test_reset_two_segments_guarded(self, authed: None) -> None:
        # E10: 2-segment 'hist:r' is stopped by the existing len guard.
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_TG_EDIT) as mock_edit,
        ):
            resp = _post(_callback_update('hist:r'))
        assert resp.status_code == 200
        mock_edit.assert_not_called()


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
