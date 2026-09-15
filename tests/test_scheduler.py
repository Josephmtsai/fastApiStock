"""Tests for the scheduler time-window functions and push routines.

Uses datetime objects directly (no freezegun needed) to test boundary cases.
"""

from datetime import datetime
from functools import partial
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from fastapistock.scheduler import (
    _previous_tw_trading_date,
    _previous_us_trading_date,
    _scheduled_push,
    build_scheduler,
    capture_tw_close_snapshot,
    capture_us_close_snapshot,
    is_tw_market_window,
    is_us_market_window,
    push_daily_pnl,
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
    def test_window_start_0930_monday_is_in(self) -> None:
        assert is_tw_market_window(_dt(0, 9, 30)) is True

    def test_before_window_0929_monday_is_out(self) -> None:
        assert is_tw_market_window(_dt(0, 9, 29)) is False

    def test_at_0830_monday_is_out(self) -> None:
        # Regression guard: 08:30 must be outside window after 013-1 change
        assert is_tw_market_window(_dt(0, 8, 30)) is False

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


_US_WINDOW_SUMMER: list[tuple[datetime, bool, str]] = [
    # (Taipei time, expected, reason) — EDT: Taipei = ET + 12h
    (datetime(2026, 7, 6, 17, 0, tzinfo=_TZ), False, 'S1 Mon 05:00 EDT premarket'),
    (datetime(2026, 7, 6, 21, 29, tzinfo=_TZ), False, 'S2 Mon 09:29 EDT'),
    (datetime(2026, 7, 6, 21, 30, tzinfo=_TZ), True, 'S3 Mon 09:30 EDT open'),
    (datetime(2026, 7, 7, 0, 0, tzinfo=_TZ), True, 'S4 Mon 12:00 EDT'),
    (datetime(2026, 7, 7, 3, 59, tzinfo=_TZ), True, 'S5 Mon 15:59 EDT'),
    (datetime(2026, 7, 7, 4, 0, tzinfo=_TZ), False, 'S6 Mon 16:00 EDT close'),
    (datetime(2026, 7, 10, 23, 0, tzinfo=_TZ), True, 'S7 Fri 11:00 EDT'),
    (datetime(2026, 7, 11, 3, 30, tzinfo=_TZ), True, 'S8 Fri 15:30 EDT'),
    (datetime(2026, 7, 11, 4, 0, tzinfo=_TZ), False, 'S9 Fri 16:00 EDT close'),
    (datetime(2026, 7, 11, 22, 0, tzinfo=_TZ), False, 'S10 Sat 10:00 EDT'),
    (datetime(2026, 7, 12, 22, 0, tzinfo=_TZ), False, 'S11 Sun 10:00 EDT'),
    (datetime(2026, 7, 13, 3, 0, tzinfo=_TZ), False, 'S12 Sun 15:00 EDT'),
]

_US_WINDOW_WINTER: list[tuple[datetime, bool, str]] = [
    # EST: Taipei = ET + 13h
    (datetime(2026, 1, 12, 17, 0, tzinfo=_TZ), False, 'W1 Mon 04:00 EST premarket'),
    (datetime(2026, 1, 12, 21, 30, tzinfo=_TZ), False, 'W2 Mon 08:30 EST'),
    (datetime(2026, 1, 12, 22, 29, tzinfo=_TZ), False, 'W3 Mon 09:29 EST'),
    (datetime(2026, 1, 12, 22, 30, tzinfo=_TZ), True, 'W4 Mon 09:30 EST open'),
    (datetime(2026, 1, 13, 4, 30, tzinfo=_TZ), True, 'W5 Mon 15:30 EST'),
    (datetime(2026, 1, 13, 4, 59, tzinfo=_TZ), True, 'W6 Mon 15:59 EST'),
    (datetime(2026, 1, 13, 5, 0, tzinfo=_TZ), False, 'W7 Mon 16:00 EST close'),
    (datetime(2026, 1, 17, 4, 30, tzinfo=_TZ), True, 'W8 Fri 15:30 EST'),
    (datetime(2026, 1, 17, 5, 0, tzinfo=_TZ), False, 'W9 Fri 16:00 EST close'),
    (datetime(2026, 1, 12, 4, 0, tzinfo=_TZ), False, 'W10 Sun 15:00 EST'),
    (datetime(2026, 1, 18, 23, 0, tzinfo=_TZ), False, 'W11 Sun 10:00 EST'),
]

_US_WINDOW_DST_SWITCH: list[tuple[datetime, bool, str]] = [
    # Spring forward 2026-03-08 (Sun); fall back 2026-11-01 (Sun)
    (datetime(2026, 3, 6, 21, 30, tzinfo=_TZ), False, 'D1 Fri 08:30 EST'),
    (datetime(2026, 3, 6, 22, 30, tzinfo=_TZ), True, 'D2 Fri 09:30 EST'),
    (datetime(2026, 3, 7, 4, 30, tzinfo=_TZ), True, 'D3 Fri 15:30 EST'),
    (datetime(2026, 3, 7, 5, 0, tzinfo=_TZ), False, 'D4 Fri 16:00 EST close'),
    (datetime(2026, 3, 9, 21, 29, tzinfo=_TZ), False, 'D5 Mon 09:29 EDT'),
    (datetime(2026, 3, 9, 21, 30, tzinfo=_TZ), True, 'D6 Mon 09:30 EDT open'),
    (datetime(2026, 3, 10, 3, 59, tzinfo=_TZ), True, 'D7 Mon 15:59 EDT'),
    (datetime(2026, 3, 10, 4, 0, tzinfo=_TZ), False, 'D8 Mon 16:00 EDT close'),
    (datetime(2026, 10, 30, 21, 30, tzinfo=_TZ), True, 'D9 Fri 09:30 EDT open'),
    (datetime(2026, 10, 31, 3, 59, tzinfo=_TZ), True, 'D10 Fri 15:59 EDT'),
    (datetime(2026, 10, 31, 4, 0, tzinfo=_TZ), False, 'D11 Fri 16:00 EDT close'),
    (datetime(2026, 11, 2, 21, 30, tzinfo=_TZ), False, 'D12 Mon 08:30 EST'),
    (datetime(2026, 11, 2, 22, 30, tzinfo=_TZ), True, 'D13 Mon 09:30 EST open'),
    (datetime(2026, 11, 3, 4, 30, tzinfo=_TZ), True, 'D14 Mon 15:30 EST'),
    (datetime(2026, 11, 3, 5, 0, tzinfo=_TZ), False, 'D15 Mon 16:00 EST close'),
]

_US_WINDOW_NAIVE: list[tuple[datetime, bool, str]] = [
    # Naive datetime is treated as Asia/Taipei wall-clock (E5)
    (datetime(2026, 7, 6, 21, 30), True, 'N1 naive -> Mon 09:30 EDT open'),
]

_UTC_TZ = ZoneInfo('UTC')

_US_WINDOW_NON_TAIPEI_AWARE: list[tuple[datetime, bool, str]] = [
    # QA-added (spec 019): non-Asia/Taipei tz-aware input must still be
    # converted correctly via astimezone(), per docstring's "any other
    # tz-aware datetime is converted correctly" contract.
    (datetime(2026, 7, 6, 13, 30, tzinfo=_UTC_TZ), True, 'UTC1 Mon 09:30 EDT open'),
    (datetime(2026, 7, 6, 13, 29, tzinfo=_UTC_TZ), False, 'UTC2 Mon 09:29 EDT'),
    (datetime(2026, 1, 12, 14, 30, tzinfo=_UTC_TZ), True, 'UTC3 Mon 09:30 EST open'),
    (datetime(2026, 1, 12, 14, 29, tzinfo=_UTC_TZ), False, 'UTC4 Mon 09:29 EST'),
]


class TestUsMarketWindow:
    """Truth table for is_us_market_window (spec 019 G1, ET-based, DST-aware).

    Window is Mon–Fri 09:30 <= t < 16:00 America/New_York; the ``reason``
    column carries the ET wall-clock so a failing row is self-explanatory.
    """

    @pytest.mark.parametrize(('now', 'expected', 'reason'), _US_WINDOW_SUMMER)
    def test_summer_edt(self, now: datetime, expected: bool, reason: str) -> None:
        assert is_us_market_window(now) is expected, reason

    @pytest.mark.parametrize(('now', 'expected', 'reason'), _US_WINDOW_WINTER)
    def test_winter_est(self, now: datetime, expected: bool, reason: str) -> None:
        assert is_us_market_window(now) is expected, reason

    @pytest.mark.parametrize(('now', 'expected', 'reason'), _US_WINDOW_DST_SWITCH)
    def test_dst_switch_weeks(self, now: datetime, expected: bool, reason: str) -> None:
        assert is_us_market_window(now) is expected, reason

    @pytest.mark.parametrize(('now', 'expected', 'reason'), _US_WINDOW_NAIVE)
    def test_naive_datetime_treated_as_taipei(
        self, now: datetime, expected: bool, reason: str
    ) -> None:
        assert is_us_market_window(now) is expected, reason

    @pytest.mark.parametrize(('now', 'expected', 'reason'), _US_WINDOW_NON_TAIPEI_AWARE)
    def test_non_taipei_aware_datetime_converted_correctly(
        self, now: datetime, expected: bool, reason: str
    ) -> None:
        assert is_us_market_window(now) is expected, reason


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

    @patch('fastapistock.scheduler._safe_send_daily_pnl_delta')
    @patch('fastapistock.scheduler.push_tw_stocks')
    @patch('fastapistock.scheduler.push_us_stocks')
    @patch('fastapistock.scheduler.is_tw_market_window', return_value=True)
    @patch('fastapistock.scheduler.is_us_market_window', return_value=False)
    def test_tw_window_sends_daily_pnl_delta(
        self,
        mock_us_win: MagicMock,
        mock_tw_win: MagicMock,
        mock_us_push: MagicMock,
        mock_tw_push: MagicMock,
        mock_pnl_delta: MagicMock,
    ) -> None:
        _scheduled_push()
        mock_tw_push.assert_called_once()
        mock_pnl_delta.assert_called_once_with('TW')

    @patch('fastapistock.scheduler._safe_send_daily_pnl_delta')
    @patch('fastapistock.scheduler.push_tw_stocks')
    @patch('fastapistock.scheduler.push_us_stocks')
    @patch('fastapistock.scheduler.is_tw_market_window', return_value=False)
    @patch('fastapistock.scheduler.is_us_market_window', return_value=True)
    def test_us_window_sends_us_daily_pnl_delta(
        self,
        mock_us_win: MagicMock,
        mock_tw_win: MagicMock,
        mock_us_push: MagicMock,
        mock_tw_push: MagicMock,
        mock_pnl_delta: MagicMock,
    ) -> None:
        _scheduled_push()
        mock_us_push.assert_called_once()
        mock_pnl_delta.assert_called_once_with('US')


class TestBuildScheduler:
    def test_returns_configured_scheduler(self) -> None:
        scheduler = build_scheduler()
        jobs = scheduler.get_jobs()
        job_ids = {job.id for job in jobs}
        assert job_ids == {
            'stock_push',
            'weekly_report',
            'monthly_report',
            'tw_daily_close_snapshot',
            'us_daily_close_snapshot',
            'daily_pnl_tw',
            'daily_pnl_us',
        }

    def test_weekly_job_calls_pipeline_with_weekly_cron(self) -> None:
        """The weekly cron job must invoke run_report_pipeline with the correct args."""
        with patch('fastapistock.scheduler.run_report_pipeline') as mock_pipeline:
            scheduler = build_scheduler()
            weekly_job = next(
                j for j in scheduler.get_jobs() if j.id == 'weekly_report'
            )
            weekly_job.func()  # invoke the partial directly
            mock_pipeline.assert_called_once_with(report_type='weekly', trigger='cron')

    def test_monthly_job_calls_pipeline_with_monthly_cron(self) -> None:
        """The monthly cron job must invoke run_report_pipeline with cron args."""
        with patch('fastapistock.scheduler.run_report_pipeline') as mock_pipeline:
            scheduler = build_scheduler()
            monthly_job = next(
                j for j in scheduler.get_jobs() if j.id == 'monthly_report'
            )
            monthly_job.func()
            mock_pipeline.assert_called_once_with(report_type='monthly', trigger='cron')

    def test_weekly_job_uses_partial_for_static_inspection(self) -> None:
        """Use functools.partial so tests can inspect args without invocation."""
        scheduler = build_scheduler()
        weekly_job = next(j for j in scheduler.get_jobs() if j.id == 'weekly_report')
        assert isinstance(weekly_job.func, partial)
        assert weekly_job.func.keywords == {
            'report_type': 'weekly',
            'trigger': 'cron',
        }

    def test_monthly_job_uses_partial_for_static_inspection(self) -> None:
        scheduler = build_scheduler()
        monthly_job = next(j for j in scheduler.get_jobs() if j.id == 'monthly_report')
        assert isinstance(monthly_job.func, partial)
        assert monthly_job.func.keywords == {
            'report_type': 'monthly',
            'trigger': 'cron',
        }


class TestDailyCloseSnapshots:
    def test_tw_close_snapshot_uses_current_tw_trading_date(self) -> None:
        with patch(
            'fastapistock.scheduler.portfolio_service.save_daily_close_snapshot',
            return_value=True,
        ) as mock_save:
            capture_tw_close_snapshot(datetime(2026, 5, 19, 14, 10, tzinfo=_TZ))

        mock_save.assert_called_once()
        assert mock_save.call_args.kwargs['market'] == 'TW'
        assert mock_save.call_args.kwargs['trading_date'] == '2026-05-19'

    def test_us_close_snapshot_uses_previous_us_trading_date(self) -> None:
        with patch(
            'fastapistock.scheduler.portfolio_service.save_daily_close_snapshot',
            return_value=True,
        ) as mock_save:
            capture_us_close_snapshot(datetime(2026, 5, 20, 4, 10, tzinfo=_TZ))

        mock_save.assert_called_once()
        assert mock_save.call_args.kwargs['market'] == 'US'
        assert mock_save.call_args.kwargs['trading_date'] == '2026-05-19'

    def test_previous_tw_trading_date_skips_weekend(self) -> None:
        monday = datetime(2026, 5, 18, 9, 0, tzinfo=_TZ)

        assert _previous_tw_trading_date(monday) == '2026-05-15'

    def test_previous_us_trading_date_monday_evening_uses_friday(self) -> None:
        monday_evening = datetime(2026, 5, 18, 17, 0, tzinfo=_TZ)

        assert _previous_us_trading_date(monday_evening) == '2026-05-15'

    def test_previous_us_trading_date_before_close_uses_prior_close(self) -> None:
        tuesday_before_close = datetime(2026, 5, 19, 3, 30, tzinfo=_TZ)

        assert _previous_us_trading_date(tuesday_before_close) == '2026-05-15'

    def test_previous_us_trading_date_winter_late_session_uses_prior_close(
        self,
    ) -> None:
        # 04:30 Tue Taipei in EST = Mon 15:30 ET, still Monday's session (E8)
        tuesday_winter_late = datetime(2026, 1, 13, 4, 30, tzinfo=_TZ)

        assert _previous_us_trading_date(tuesday_winter_late) == '2026-01-09'


class TestMonthlyReportTrigger:
    """Verify the monthly_report job uses the first-Sunday CronTrigger (008)."""

    def _get_monthly_trigger(self) -> object:
        scheduler = build_scheduler()
        monthly_job = next(j for j in scheduler.get_jobs() if j.id == 'monthly_report')
        return monthly_job.trigger

    def test_monthly_trigger_has_day_of_week_sun(self) -> None:
        """day_of_week field must be 'sun' (every Sunday)."""
        trigger = self._get_monthly_trigger()
        fields = {f.name: f for f in trigger.fields}  # type: ignore[attr-defined]
        assert str(fields['day_of_week']) == 'sun'

    def test_monthly_trigger_has_day_range_1_to_7(self) -> None:
        """day field must restrict to 1-7 so only the first Sunday fires."""
        trigger = self._get_monthly_trigger()
        fields = {f.name: f for f in trigger.fields}  # type: ignore[attr-defined]
        assert str(fields['day']) == '1-7'

    def test_monthly_trigger_has_no_day_equals_1_only(self) -> None:
        """The old trigger used day=1; the new trigger must not match only day=1."""
        trigger = self._get_monthly_trigger()
        fields = {f.name: f for f in trigger.fields}  # type: ignore[attr-defined]
        # day field should be the range expression '1-7', not a single '1'
        assert str(fields['day']) != '1'

    def test_monthly_job_name_updated(self) -> None:
        """Job name must reflect first-Sunday semantics."""
        scheduler = build_scheduler()
        monthly_job = next(j for j in scheduler.get_jobs() if j.id == 'monthly_report')
        assert 'first Sunday' in monthly_job.name

    def test_weekly_trigger_unchanged(self) -> None:
        """Modifying monthly trigger must not affect the weekly_report trigger."""
        scheduler = build_scheduler()
        weekly_job = next(j for j in scheduler.get_jobs() if j.id == 'weekly_report')
        fields = {f.name: f for f in weekly_job.trigger.fields}  # type: ignore[attr-defined]
        # Weekly job fires every Sunday without a day restriction
        assert str(fields['day_of_week']) == 'sun'
        # The weekly trigger should NOT have a day restriction of 1-7
        assert str(fields['day']) == '*'


# ── push_daily_pnl ──────────────────────────────────────────────────────────


class TestPushDailyPnl:
    def test_push_daily_pnl_sends_all_segments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """push_daily_pnl must send every segment from build_pnl_report."""
        monkeypatch.setattr('fastapistock.scheduler.TELEGRAM_USER_ID', '999')

        sent: list[tuple[str, str, dict[str, object]]] = []

        def _fake_send(uid: str, text: str, **kw: object) -> None:
            sent.append((uid, text, kw))

        monkeypatch.setattr('fastapistock.scheduler.send_text_message', _fake_send)
        with patch(
            'fastapistock.scheduler.build_pnl_report', return_value=['seg1', 'seg2']
        ):
            push_daily_pnl()

        assert len(sent) == 2
        assert all(kw.get('parse_mode') == 'MarkdownV2' for _, _, kw in sent)

    def test_push_daily_pnl_no_user_id_skips(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr('fastapistock.scheduler.TELEGRAM_USER_ID', '')
        with patch('fastapistock.scheduler.build_pnl_report') as mock_build:
            push_daily_pnl()
        mock_build.assert_not_called()

    def test_push_daily_pnl_exception_is_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exceptions from build_pnl_report must not propagate."""
        monkeypatch.setattr('fastapistock.scheduler.TELEGRAM_USER_ID', '999')
        with patch(
            'fastapistock.scheduler.build_pnl_report',
            side_effect=RuntimeError('boom'),
        ):
            push_daily_pnl()  # must not raise


class TestDailyPnlJobTriggers:
    def test_tw_pnl_job_fires_weekdays_at_1435(self) -> None:
        scheduler = build_scheduler()
        job = next(j for j in scheduler.get_jobs() if j.id == 'daily_pnl_tw')
        fields = {f.name: f for f in job.trigger.fields}  # type: ignore[attr-defined]
        assert str(fields['hour']) == '14'
        assert str(fields['minute']) == '35'
        assert str(fields['day_of_week']) == 'mon-fri'

    def test_us_pnl_job_fires_tue_sat_at_0405(self) -> None:
        scheduler = build_scheduler()
        job = next(j for j in scheduler.get_jobs() if j.id == 'daily_pnl_us')
        fields = {f.name: f for f in job.trigger.fields}  # type: ignore[attr-defined]
        assert str(fields['hour']) == '4'
        assert str(fields['minute']) == '5'
        assert str(fields['day_of_week']) == 'tue-sat'


# ── Timezone Guard ──────────────────────────────────────────────────────────


class TestTwMarketWindowTimezone:
    """Verify is_tw_market_window interprets .hour/.minute as Asia/Taipei wall clock.

    The function contract requires callers to pass an Asia/Taipei-aware datetime.
    _scheduled_push() always does datetime.now(_TZ) so production is safe.
    These tests guard that the boundary logic is correct for Asia/Taipei times.
    """

    def test_0930_taipei_is_in_window(self) -> None:
        """09:30 Asia/Taipei wall clock -> inside window."""
        dt = datetime(2026, 4, 6, 9, 30, tzinfo=_TZ)
        assert is_tw_market_window(dt) is True

    def test_0929_taipei_is_out_of_window(self) -> None:
        """09:29 Asia/Taipei wall clock -> outside window (one minute before open)."""
        dt = datetime(2026, 4, 6, 9, 29, tzinfo=_TZ)
        assert is_tw_market_window(dt) is False

    def test_1400_taipei_is_in_window(self) -> None:
        """14:00 Asia/Taipei wall clock -> inside window (last minute)."""
        dt = datetime(2026, 4, 6, 14, 0, tzinfo=_TZ)
        assert is_tw_market_window(dt) is True

    def test_1401_taipei_is_out_of_window(self) -> None:
        """14:01 Asia/Taipei wall clock -> outside window (one minute after close)."""
        dt = datetime(2026, 4, 6, 14, 1, tzinfo=_TZ)
        assert is_tw_market_window(dt) is False
