"""Supplemental QA tests for spec-018 (/history chart + quick buttons).

Covers scenarios beyond the developer suite:

* Repeated ``g`` steps (user hammering the chart button) — stateless, no
  figure-state accumulation, no exception.
* Weekly/monthly toggle roundtrip — keyboard and content stay consistent.
* ``hist:r:menu`` reset followed by a complete re-selection flow.
* Extreme values (negative PnL, huge totals, huge pnl_pct) still render.
* Summary chart axis labels carry the correct currency per market; ALL
  renders two stacked sharex subplots (spec-019).
* ``sendPhoto`` caption is plain text (no ``parse_mode``) so Markdown
  metacharacters cannot break delivery.
* ``g`` step segment-count guards (E10 analogue for the chart step).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from matplotlib.figure import Figure

from fastapistock.main import app
from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
)
from fastapistock.services import chart_service
from fastapistock.services.telegram_service import send_photo

client = TestClient(app)

_TZ = ZoneInfo('Asia/Taipei')
_VALID_SECRET = 'test-secret'  # noqa: S105 — test fixture
_AUTHORIZED_ID = 99999
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

_PATCH_SECRET = 'fastapistock.routers.webhook.config.TELEGRAM_WEBHOOK_SECRET'  # noqa: S105
_PATCH_USER = 'fastapistock.routers.webhook.config.TELEGRAM_USER_ID'
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


@pytest.fixture
def authed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_PATCH_SECRET, _VALID_SECRET)
    monkeypatch.setattr(_PATCH_USER, str(_AUTHORIZED_ID))


def _post_callback(data: str) -> object:
    payload = {
        'update_id': 2,
        'callback_query': {
            'id': 'cbq-qa',
            'from': {'id': _AUTHORIZED_ID, 'is_bot': False, 'first_name': 'QA'},
            'message': {
                'message_id': 555,
                'from': {'id': _AUTHORIZED_ID, 'is_bot': False, 'first_name': 'QA'},
                'chat': {'id': _AUTHORIZED_ID},
                'text': '舊訊息',
            },
            'data': data,
        },
    }
    return client.post(
        '/api/v1/webhook/telegram',
        json=payload,
        headers={'X-Telegram-Bot-Api-Secret-Token': _VALID_SECRET},
    )


def _button_data(markup: dict[str, object]) -> list[str]:
    return [
        btn['callback_data']
        for row in markup['inline_keyboard']  # type: ignore[union-attr]
        for btn in row
    ]


def _snapshot(
    *,
    period: str,
    price: str = '800',
    cost: str = '700',
    pnl: str = '100000',
    pnl_pct: str | None = '14.29',
) -> SymbolSnapshot:
    return SymbolSnapshot(
        report_type='monthly',
        report_period=period,
        market='TW',
        symbol='2330',
        shares=Decimal('1000'),
        avg_cost=Decimal(cost),
        current_price=Decimal(price),
        market_value=Decimal(price) * 1000,
        unrealized_pnl=Decimal(pnl),
        pnl_pct=Decimal(pnl_pct) if pnl_pct is not None else None,
        pnl_delta=None,
        captured_at=datetime(2026, 6, 1, 21, 0, tzinfo=_TZ),
    )


def _summary(
    *,
    period: str,
    tw: str = '500000',
    us: str = '8000',
) -> ReportSummary:
    return ReportSummary(
        report_type='monthly',
        report_period=period,
        pnl_tw_total=Decimal(tw),
        pnl_us_total=Decimal(us),
        pnl_tw_delta=None,
        pnl_us_delta=None,
        buy_amount_twd=None,
        signals_count=0,
        symbols_count=5,
        captured_at=datetime(2026, 6, 1, 21, 0, tzinfo=_TZ),
    )


# ── Repeated g steps: stateless rendering ──────────────────────────────────


class TestRepeatedChartClicks:
    """Hammering the chart button must not accumulate figure state."""

    def test_five_symbol_chart_clicks_render_identically(self, authed: None) -> None:
        rows = [
            _snapshot(period='2026-02'),
            _snapshot(period='2026-03', price='750'),
            _snapshot(period='2026-04', price='820'),
        ]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows),
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
            patch(_PATCH_TG_REPLY, return_value=True) as mock_reply,
        ):
            for _ in range(5):
                resp = _post_callback('hist:g:symbol:TW:2330:monthly')
                assert resp.status_code == 200
        assert mock_photo.call_count == 5
        mock_reply.assert_not_called()
        pngs = [call.args[1] for call in mock_photo.call_args_list]
        assert all(png.startswith(_PNG_MAGIC) for png in pngs)
        # Stateless rendering: same input → byte-identical output. Any
        # cross-call figure-state accumulation would change the bytes.
        assert all(png == pngs[0] for png in pngs)

    def test_five_summary_chart_clicks_no_exception(self, authed: None) -> None:
        rows = [_summary(period='2026-02'), _summary(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SUMMARY, return_value=rows),
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
        ):
            for _ in range(5):
                resp = _post_callback('hist:g:summary:ALL:monthly')
                assert resp.status_code == 200
        assert mock_photo.call_count == 5
        pngs = [call.args[1] for call in mock_photo.call_args_list]
        assert all(png == pngs[0] for png in pngs)


# ── Toggle roundtrip consistency ───────────────────────────────────────────


class TestToggleRoundtrip:
    """monthly → weekly → monthly keeps keyboard and content consistent."""

    def test_roundtrip_restores_original_keyboard(self, authed: None) -> None:
        rows = [_snapshot(period='2026-02'), _snapshot(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows),
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            assert _post_callback('hist:p:symbol:TW:2330:monthly').status_code == 200
            first = mock_edit.call_args.kwargs
            assert _post_callback('hist:p:symbol:TW:2330:weekly').status_code == 200
            weekly = mock_edit.call_args.kwargs
            assert _post_callback('hist:p:symbol:TW:2330:monthly').status_code == 200
            final = mock_edit.call_args.kwargs
        # Weekly page carries weekly chart payload + back-to-monthly toggle.
        weekly_buttons = _button_data(weekly['reply_markup'])
        assert 'hist:g:symbol:TW:2330:weekly' in weekly_buttons
        assert 'hist:p:symbol:TW:2330:monthly' in weekly_buttons
        assert '週報' in weekly['text']
        # Roundtrip: final monthly page identical to the first monthly page.
        assert final['reply_markup'] == first['reply_markup']
        assert final['text'] == first['text']
        assert '月報' in final['text']


# ── Reset then full re-selection flow ──────────────────────────────────────


class TestResetThenFullFlow:
    """hist:r:menu then walking the whole menu again works end to end."""

    def test_reset_then_symbol_flow_reaches_result_page(self, authed: None) -> None:
        options = {
            'markets': ['TW', 'US'],
            'report_types': ['weekly', 'monthly'],
            'symbols': {'TW': ['2330', '0050'], 'US': ['AAPL']},
            'periods': {'weekly': [], 'monthly': ['2026-04']},
            'latest_captured_at': '2026-05-01T21:00:00+08:00',
        }
        rows = [_snapshot(period='2026-03'), _snapshot(period='2026-04')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_OPTIONS, return_value=options),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows),
            patch(_PATCH_TG_EDIT, return_value=True) as mock_edit,
        ):
            # Reset from an arbitrary result page back to the type menu.
            assert _post_callback('hist:r:menu').status_code == 200
            menu = mock_edit.call_args.kwargs
            assert '請選擇查詢類型' in menu['text']
            assert 'hist:t:symbol' in _button_data(menu['reply_markup'])
            # Walk the full symbol flow again from that menu.
            assert _post_callback('hist:t:symbol').status_code == 200
            assert 'hist:m:symbol:TW' in _button_data(
                mock_edit.call_args.kwargs['reply_markup']
            )
            assert _post_callback('hist:m:symbol:TW').status_code == 200
            assert 'hist:s:TW:2330' in _button_data(
                mock_edit.call_args.kwargs['reply_markup']
            )
            assert _post_callback('hist:s:TW:2330').status_code == 200
            assert 'hist:p:symbol:TW:2330:monthly' in _button_data(
                mock_edit.call_args.kwargs['reply_markup']
            )
            assert _post_callback('hist:p:symbol:TW:2330:monthly').status_code == 200
            result = mock_edit.call_args.kwargs
        assert '2330' in result['text']
        assert 'hist:g:symbol:TW:2330:monthly' in _button_data(result['reply_markup'])
        assert mock_edit.call_count == 5


# ── Extreme values ─────────────────────────────────────────────────────────


class TestExtremeValueRendering:
    """Negative PnL, huge totals and huge pnl_pct must not break rendering."""

    def test_symbol_chart_deep_negative_and_huge_pct(self) -> None:
        rows = [
            _snapshot(period='2026-01', price='0.01', cost='999999', pnl_pct='-99.99'),
            _snapshot(
                period='2026-02',
                price='99999999.99',
                cost='0.01',
                pnl_pct='999999999.99',
            ),
        ]
        png = chart_service.render_symbol_chart(rows)
        assert png.startswith(_PNG_MAGIC)
        assert len(png) > 1024

    def test_summary_chart_extreme_totals_all_markets(self) -> None:
        rows = [
            _summary(period='2026-01', tw='-999999999999.99', us='-0.01'),
            _summary(period='2026-02', tw='999999999999.99', us='123456789.99'),
        ]
        for market in ('TW', 'US', 'ALL'):
            png = chart_service.render_summary_chart(rows, market=market)
            assert png.startswith(_PNG_MAGIC)

    def test_summary_chart_constant_zero_series(self) -> None:
        rows = [
            _summary(period='2026-01', tw='0', us='0'),
            _summary(period='2026-02', tw='0', us='0'),
        ]
        png = chart_service.render_summary_chart(rows, market='ALL')
        assert png.startswith(_PNG_MAGIC)


# ── Axis labels (spec-018 AC-2.x; spec-019 AC-1.x / AC-2.1 / AC-4.x) ──────


class TestSummaryAxisLabels:
    """Axis titles, currencies and stacked-subplot layout per market."""

    def _capture_figure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> list[Figure]:
        captured: list[Figure] = []
        original: Callable[[Figure], bytes] = chart_service._fig_to_png

        def spy(fig: Figure) -> bytes:
            captured.append(fig)
            return original(fig)

        monkeypatch.setattr(chart_service, '_fig_to_png', spy)
        return captured

    def test_us_single_market_axis_says_usd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = self._capture_figure(monkeypatch)
        chart_service.render_summary_chart(
            [_summary(period='2026-02'), _summary(period='2026-03')], market='US'
        )
        axes = captured[0].axes
        assert len(axes) == 1
        assert axes[0].get_ylabel() == 'US P&L (USD)'
        assert 'TWD' not in axes[0].get_ylabel()
        assert axes[0].get_xlabel() == 'Report period (monthly)'
        assert axes[0].yaxis.get_major_formatter()(610000) == '610,000'

    def test_tw_single_market_axis_says_twd(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = self._capture_figure(monkeypatch)
        chart_service.render_summary_chart([_summary(period='2026-03')], market='TW')
        axes = captured[0].axes
        assert len(axes) == 1
        assert axes[0].get_ylabel() == 'TW P&L (TWD)'
        assert axes[0].get_xlabel() == 'Report period (monthly)'
        assert axes[0].yaxis.get_major_formatter()(610000) == '610,000'

    def test_all_market_stacked_subplots_currencies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # spec-019 AC-4.1 / AC-4.3: ALL is two stacked sharex subplots
        # (TW on top, US below), not a twinx right axis.
        captured = self._capture_figure(monkeypatch)
        chart_service.render_summary_chart([_summary(period='2026-03')], market='ALL')
        axes = captured[0].axes
        assert len(axes) == 2
        assert axes[0].get_ylabel() == 'TW P&L (TWD)'
        assert axes[1].get_ylabel() == 'US P&L (USD)'
        assert axes[0].get_position().y0 > axes[1].get_position().y0
        assert axes[1].yaxis.get_ticks_position() == 'left'
        assert axes[0].get_shared_x_axes().joined(axes[0], axes[1])
        assert axes[0].get_xlabel() == ''
        assert axes[1].get_xlabel() == 'Report period (monthly)'

    def test_symbol_chart_legend_and_title(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = self._capture_figure(monkeypatch)
        chart_service.render_symbol_chart(
            [_snapshot(period='2026-02'), _snapshot(period='2026-03')]
        )
        ax = captured[0].axes[0]
        legend = ax.get_legend()
        assert legend is not None
        labels = [t.get_text() for t in legend.get_texts()]
        assert labels == ['close', 'avg cost']
        assert ax.get_title() == '2330 (TW) monthly'
        assert ax.get_ylabel() == 'Price (TWD)'
        assert ax.get_xlabel() == 'Report period (monthly)'


# ── Caption safety: plain text, no parse_mode ──────────────────────────────


class TestCaptionSafety:
    """sendPhoto caption must be plain text so symbols cannot break it."""

    @patch('fastapistock.services.telegram_service.TELEGRAM_TOKEN', 'tok')
    @patch('fastapistock.services.telegram_service.httpx.post')
    def test_send_photo_payload_has_no_parse_mode(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp
        caption = '📈 BRK.B (US) 月報 _*[]()~`>#+-=|{}.!'
        assert send_photo(1, _PNG_MAGIC, caption=caption) is True
        kwargs = mock_post.call_args.kwargs
        assert 'parse_mode' not in kwargs['data']
        assert 'json' not in kwargs
        # Metacharacters are forwarded verbatim (plain text, no escaping).
        assert kwargs['data']['caption'] == caption

    def test_symbol_chart_caption_is_plain_and_descriptive(self, authed: None) -> None:
        rows = [_snapshot(period='2026-03')]
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL, return_value=rows),
            patch(_PATCH_TG_SEND_PHOTO, return_value=True) as mock_photo,
        ):
            resp = _post_callback('hist:g:symbol:TW:2330:weekly')
        assert resp.status_code == 200
        caption = mock_photo.call_args.kwargs['caption']
        assert '2330' in caption
        assert '週報' in caption


# ── g-step segment guards (E10 analogue) ───────────────────────────────────


class TestChartStepGuards:
    """Short or unknown g-step payloads are dropped without side effects."""

    @pytest.mark.parametrize(
        'data',
        [
            'hist:g:symbol',  # 3 segments
            'hist:g:symbol:TW',  # 4 segments
            'hist:g:symbol:TW:2330',  # symbol flow missing period
            'hist:g:unknown:TW:monthly',  # unknown flow keyword
        ],
    )
    def test_short_or_unknown_g_payload_dropped(self, authed: None, data: str) -> None:
        with (
            patch(_PATCH_TG_ANSWER, return_value=True),
            patch(_PATCH_REPO_LIST_SYMBOL) as mock_sym,
            patch(_PATCH_REPO_LIST_SUMMARY) as mock_sum,
            patch(_PATCH_TG_SEND_PHOTO) as mock_photo,
            patch(_PATCH_TG_REPLY) as mock_reply,
        ):
            resp = _post_callback(data)
        assert resp.status_code == 200
        mock_sym.assert_not_called()
        mock_sum.assert_not_called()
        mock_photo.assert_not_called()
        mock_reply.assert_not_called()
