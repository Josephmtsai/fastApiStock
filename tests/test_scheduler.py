"""Tests for the scheduler time-window functions and push routines.

Uses datetime objects directly (no freezegun needed) to test boundary cases.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from fastapistock.scheduler import (
    _scheduled_push,
    build_scheduler,
    is_tw_market_window,
    is_us_market_window,
    push_tw_stocks,
    push_us_stocks,
)

_TZ = ZoneInfo('Asia/Taipei')


def _dt(weekday_offset: int, hour: int, minute: int = 0) -> datetime:
    """Build a datetime in Asia/Taipei for a given weekday offset from Monday.

    Args:
        weekday_offset: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun.
        hour: Hour (0–23).
        minute: Minute (0–59).

    Returns:
        Timezone-aware datetime in Asia/Taipei.
    """
    # 2026-04-06 is a Monday
    from datetime import timedelta

    base_monday = datetime(2026, 4, 6, tzinfo=_TZ)
    return base_monday + timedelta(days=weekday_offset, hours=hour, minutes=minute)


# ── Taiwan Market Window ────────────────────────────────────────────────────


class TestTwMarketWindow:
    def test_window_start_0830_monday_is_in(self) -> None:
        assert is_tw_market_window(_dt(0, 8, 30)) is True

    def test_before_window_0829_monday_is_out(self) -> None:
        assert is_tw_market_window(_dt(0, 8, 29)) is False

    def test_window_end_1400_friday_is_in(self) -> None:
        assert is_tw_market_window(_dt(4, 14, 0)) is True

    def test_after_window_1401_friday_is_out(self) -> None:
        assert is_tw_market_window(_dt(4, 14, 1)) is False

    def test_saturday_0900_is_out(self) -> None:
        assert is_tw_market_window(_dt(5, 9, 0)) is False

    def test_sunday_1000_is_out(self) -> None:
        assert is_tw_market_window(_dt(6, 10, 0)) is False

    def test_midday_wednesday_is_in(self) -> None:
        assert is_tw_market_window(_dt(2, 11, 0)) is True

    def test_0800_monday_is_out(self) -> None:
        assert is_tw_market_window(_dt(0, 8, 0)) is False


# ── US Market Window ────────────────────────────────────────────────────────


class TestUsMarketWindow:
    def test_1700_wednesday_is_in(self) -> None:
        assert is_us_market_window(_dt(2, 17, 0)) is True

    def test_1659_wednesday_is_out(self) -> None:
        assert is_us_market_window(_dt(2, 16, 59)) is False

    def test_0400_thursday_is_in(self) -> None:
        # 04:00 Thu = continuation of Wed evening session
        assert is_us_market_window(_dt(3, 4, 0)) is True

    def test_0401_thursday_is_out(self) -> None:
        assert is_us_market_window(_dt(3, 4, 1)) is False

    def test_sunday_2000_is_out(self) -> None:
        assert is_us_market_window(_dt(6, 20, 0)) is False

    def test_saturday_0300_is_in(self) -> None:
        # 03:00 Sat = continuation of Fri evening session
        assert is_us_market_window(_dt(5, 3, 0)) is True

    def test_saturday_0500_is_out(self) -> None:
        assert is_us_market_window(_dt(5, 5, 0)) is False

    def test_monday_0300_is_out(self) -> None:
        # 03:00 Mon = would be Sun evening, which has no US session
        assert is_us_market_window(_dt(0, 3, 0)) is False

    def test_friday_1700_is_in(self) -> None:
        assert is_us_market_window(_dt(4, 17, 0)) is True

    def test_friday_2300_is_in(self) -> None:
        assert is_us_market_window(_dt(4, 23, 0)) is True

    def test_tuesday_0000_is_in(self) -> None:
        # 00:00 Tue = continuation of Mon evening
        assert is_us_market_window(_dt(1, 0, 0)) is True

    def test_saturday_0400_is_in(self) -> None:
        # Exactly 04:00 Sat = last valid tick
        assert is_us_market_window(_dt(5, 4, 0)) is True


# ── Push Functions ─────────────────────────────────────────────────────────


class TestPushTwStocks:
    @patch('fastapistock.scheduler.TELEGRAM_USER_ID', '')
    def test_skips_when_no_user_id(self) -> None:
        push_tw_stocks()  # should return early without error

    @patch('fastapistock.scheduler.tw_stock_codes', return_value=[])
    @patch('fastapistock.scheduler.TELEGRAM_USER_ID', '123456')
    def test_skips_when_no_codes(self, mock_codes: MagicMock) -> None:
        push_tw_stocks()
        mock_codes.assert_called_once()

    @patch('fastapistock.scheduler.TELEGRAM_USER_ID', '123456')
    @patch('fastapistock.scheduler.tw_stock_codes', return_value=['0050'])
    @patch(
        'fastapistock.services.stock_service.get_rich_tw_stocks',
        return_value=[],
    )
    @patch(
        'fastapistock.services.telegram_service.send_rich_stock_message',
        return_value=True,
    )
    def test_calls_send_when_configured(
        self,
        mock_send: MagicMock,
        mock_get: MagicMock,
        mock_codes: MagicMock,
    ) -> None:
        push_tw_stocks()
        mock_codes.assert_called_once()

    @patch('fastapistock.scheduler.TELEGRAM_USER_ID', '123456')
    @patch('fastapistock.scheduler.tw_stock_codes', return_value=['0050'])
    @patch(
        'fastapistock.services.stock_service.get_rich_tw_stocks',
        side_effect=RuntimeError('boom'),
    )
    def test_exception_is_caught(
        self, mock_get: MagicMock, mock_codes: MagicMock
    ) -> None:
        push_tw_stocks()  # should not raise


class TestPushUsStocks:
    @patch('fastapistock.scheduler.TELEGRAM_USER_ID', '')
    def test_skips_when_no_user_id(self) -> None:
        push_us_stocks()

    @patch('fastapistock.scheduler.us_stock_symbols', return_value=[])
    @patch('fastapistock.scheduler.TELEGRAM_USER_ID', '123456')
    def test_skips_when_no_symbols(self, mock_syms: MagicMock) -> None:
        push_us_stocks()
        mock_syms.assert_called_once()

    @patch('fastapistock.scheduler.TELEGRAM_USER_ID', '123456')
    @patch('fastapistock.scheduler.us_stock_symbols', return_value=['AAPL'])
    @patch(
        'fastapistock.services.us_stock_service.get_us_stocks',
        side_effect=RuntimeError('boom'),
    )
    def test_exception_is_caught(
        self, mock_get: MagicMock, mock_syms: MagicMock
    ) -> None:
        push_us_stocks()  # should not raise


class TestScheduledPush:
    @patch('fastapistock.scheduler.push_tw_stocks')
    @patch('fastapistock.scheduler.push_us_stocks')
    @patch('fastapistock.scheduler.is_tw_market_window', return_value=True)
    @patch('fastapistock.scheduler.is_us_market_window', return_value=False)
    def test_tw_window_calls_tw_push(
        self,
        mock_us_win: MagicMock,
        mock_tw_win: MagicMock,
        mock_us_push: MagicMock,
        mock_tw_push: MagicMock,
    ) -> None:
        _scheduled_push()
        mock_tw_push.assert_called_once()
        mock_us_push.assert_not_called()

    @patch('fastapistock.scheduler.push_tw_stocks')
    @patch('fastapistock.scheduler.push_us_stocks')
    @patch('fastapistock.scheduler.is_tw_market_window', return_value=False)
    @patch('fastapistock.scheduler.is_us_market_window', return_value=True)
    def test_us_window_calls_us_push(
        self,
        mock_us_win: MagicMock,
        mock_tw_win: MagicMock,
        mock_us_push: MagicMock,
        mock_tw_push: MagicMock,
    ) -> None:
        _scheduled_push()
        mock_us_push.assert_called_once()
        mock_tw_push.assert_not_called()


class TestBuildScheduler:
    def test_returns_configured_scheduler(self) -> None:
        scheduler = build_scheduler()
        jobs = scheduler.get_jobs()
        job_ids = {job.id for job in jobs}
        assert job_ids == {'stock_push', 'weekly_report', 'monthly_report'}
