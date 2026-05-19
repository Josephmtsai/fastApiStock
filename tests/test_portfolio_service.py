"""Unit tests for portfolio_service PnL formatting."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fastapistock.repositories.portfolio_snapshot_repo import PortfolioSnapshot
from fastapistock.services import portfolio_service
from fastapistock.services.portfolio_service import (
    _format_pnl_reply,
    format_market_daily_pnl_delta,
)

_TZ = ZoneInfo('Asia/Taipei')


class TestFormatPnlReply:
    def test_both_positive_values(self) -> None:
        result = _format_pnl_reply(1_234_567.0, 890_123.0)
        assert '📈 投資組合未實現損益' in result
        assert '🇹🇼 台股：$+1,234,567 TWD' in result
        assert '🇺🇸 美股：$+890,123 TWD' in result
        assert '合計：$+2,124,690 TWD' in result

    def test_negative_tw_positive_us(self) -> None:
        result = _format_pnl_reply(-123_456.0, 890_123.0)
        assert '🇹🇼 台股：$-123,456 TWD' in result
        assert '🇺🇸 美股：$+890,123 TWD' in result
        assert '合計：$+766,667 TWD' in result

    def test_tw_none_partial_failure(self) -> None:
        result = _format_pnl_reply(None, 890_123.0)
        assert '🇹🇼 台股：無法取得' in result
        assert '🇺🇸 美股：$+890,123 TWD' in result
        assert '合計：無法計算（部分資料缺失）' in result

    def test_us_none_partial_failure(self) -> None:
        result = _format_pnl_reply(1_234_567.0, None)
        assert '🇹🇼 台股：$+1,234,567 TWD' in result
        assert '🇺🇸 美股：無法取得' in result
        assert '合計：無法計算（部分資料缺失）' in result

    def test_both_none_total_failure(self) -> None:
        result = _format_pnl_reply(None, None)
        assert '📈 投資組合未實現損益' in result
        assert '無法取得損益資料，請稍後再試' in result
        assert '台股' not in result
        assert '美股' not in result

    def test_zero_value(self) -> None:
        result = _format_pnl_reply(0.0, 0.0)
        assert '🇹🇼 台股：$+0 TWD' in result
        assert '🇺🇸 美股：$+0 TWD' in result
        assert '合計：$+0 TWD' in result


class TestDailyPnlDelta:
    def test_format_market_daily_pnl_delta_complete_us(self) -> None:
        text = format_market_daily_pnl_delta(
            market='US',
            current_pnl=350000.0,
            previous_pnl=320000.0,
        )

        assert 'US PnL vs previous close' in text
        assert 'Current: +350,000 TWD' in text
        assert 'Previous close: +320,000 TWD' in text
        assert 'Change: +30,000 TWD' in text

    def test_format_market_daily_pnl_delta_missing_us_baseline(self) -> None:
        text = format_market_daily_pnl_delta(
            market='US',
            current_pnl=350000.0,
            previous_pnl=None,
        )

        assert 'No US previous-close baseline yet.' in text
        assert 'Current: +350,000 TWD' in text
        assert 'Current total' not in text

    def test_format_market_daily_pnl_delta_current_unavailable(
        self,
    ) -> None:
        text = format_market_daily_pnl_delta(
            market='US',
            current_pnl=None,
            previous_pnl=None,
        )

        assert 'US current PnL unavailable.' in text
        assert '+0 TWD' not in text

    def test_format_market_daily_pnl_delta_tw_does_not_show_us_or_total(
        self,
    ) -> None:
        text = format_market_daily_pnl_delta(
            market='TW',
            current_pnl=108000.0,
            previous_pnl=100000.0,
        )

        assert 'TW PnL vs previous close' in text
        assert 'Change: +8,000 TWD' in text
        assert 'US:' not in text
        assert 'Total:' not in text

    def test_save_daily_close_snapshot_tw(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved: dict[str, object] = {}
        monkeypatch.setattr(portfolio_service, 'fetch_pnl_tw', lambda: 5000.0)
        monkeypatch.setattr(
            portfolio_service.portfolio_snapshot_repo,
            'save_daily',
            lambda market, trading_date, snapshot: saved.update(
                {
                    'market': market,
                    'trading_date': trading_date,
                    'snapshot': snapshot,
                }
            ),
        )

        ok = portfolio_service.save_daily_close_snapshot(
            market='TW',
            trading_date='2026-05-19',
            captured_at=datetime(2026, 5, 19, 14, 10, tzinfo=_TZ),
        )

        assert ok is True
        assert saved['market'] == 'TW'
        assert saved['trading_date'] == '2026-05-19'
        assert isinstance(saved['snapshot'], PortfolioSnapshot)

    def test_get_daily_pnl_delta_reply_uses_us_daily_baseline_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(portfolio_service, 'fetch_pnl_tw', lambda: 108000.0)
        monkeypatch.setattr(portfolio_service, 'fetch_pnl_us', lambda: 12000.0)

        def fake_get_daily(market: str, trading_date: str) -> PortfolioSnapshot | None:
            if market == 'TW' and trading_date == '2026-05-19':
                return PortfolioSnapshot(
                    pnl_tw=100000.0,
                    pnl_us=0.0,
                    timestamp=datetime(2026, 5, 19, 14, 10, tzinfo=_TZ),
                )
            if market == 'US' and trading_date == '2026-05-19':
                return PortfolioSnapshot(
                    pnl_tw=0.0,
                    pnl_us=15000.0,
                    timestamp=datetime(2026, 5, 20, 4, 10, tzinfo=_TZ),
                )
            return None

        monkeypatch.setattr(
            portfolio_service.portfolio_snapshot_repo,
            'get_daily',
            fake_get_daily,
        )

        text = portfolio_service.get_daily_pnl_delta_reply(
            market='US', trading_date='2026-05-19'
        )

        assert 'US PnL vs previous close' in text
        assert 'Change: -3,000 TWD' in text
        assert 'TW:' not in text
        assert 'Total:' not in text
