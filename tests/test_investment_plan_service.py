"""Unit tests for investment_plan_service: achievement rate and formatting."""

from datetime import date
from unittest.mock import patch

import pytest

from fastapistock.repositories.investment_plan_repo import InvestmentPlanEntry
from fastapistock.services.investment_plan_service import (
    QuarterlyAchievementReport,
    format_achievement_reply,
    get_quarterly_achievement_rate,
)

_MOCK_FETCH = 'fastapistock.services.investment_plan_service.fetch_investment_plan'

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_TODAY = date(2026, 4, 10)
_Q2_START = date(2026, 4, 1)
_Q2_END = date(2026, 6, 30)


def _entry(
    symbol: str,
    expected: float,
    invested: float,
    start: date = _Q2_START,
    end: date = _Q2_END,
) -> InvestmentPlanEntry:
    return InvestmentPlanEntry(
        symbol=symbol,
        start_date=start,
        end_date=end,
        expected_usd=expected,
        invested_usd=invested,
    )


# ---------------------------------------------------------------------------
# get_quarterly_achievement_rate
# ---------------------------------------------------------------------------


def test_normal_rate_calculation() -> None:
    entries = [
        _entry('AAPL', 1000.0, 500.0),
        _entry('TSLA', 500.0, 250.0),
    ]
    with patch(_MOCK_FETCH, return_value=entries):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is not None
    assert report.total_expected == pytest.approx(1500.0)
    assert report.total_invested == pytest.approx(750.0)
    assert report.rate_pct == pytest.approx(50.0)
    assert set(report.symbols) == {'AAPL', 'TSLA'}


def test_no_active_quarter_returns_none() -> None:
    """No entries cover today → returns None."""
    past_entry = _entry(
        'AAPL', 1000.0, 500.0, start=date(2026, 1, 1), end=date(2026, 3, 31)
    )
    with patch(_MOCK_FETCH, return_value=[past_entry]):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is None


def test_empty_plan_returns_none() -> None:
    with patch(_MOCK_FETCH, return_value=[]):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is None


def test_denominator_zero_sentinel() -> None:
    """When total expected = 0, rate_pct is set to sentinel -1.0."""
    entries = [_entry('AAPL', 0.0, 500.0)]
    with patch(_MOCK_FETCH, return_value=entries):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is not None
    assert report.rate_pct == pytest.approx(-1.0)


def test_over_achievement_above_100() -> None:
    entries = [_entry('NVDA', 100.0, 200.0)]
    with patch(_MOCK_FETCH, return_value=entries):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is not None
    assert report.rate_pct == pytest.approx(200.0)


def test_boundary_start_date_included() -> None:
    """Entry whose start_date == today should be included."""
    entries = [_entry('AAPL', 1000.0, 500.0, start=_TODAY, end=date(2026, 6, 30))]
    with patch(_MOCK_FETCH, return_value=entries):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is not None


def test_boundary_end_date_included() -> None:
    """Entry whose end_date == today should be included."""
    entries = [_entry('AAPL', 1000.0, 500.0, start=date(2026, 1, 1), end=_TODAY)]
    with patch(_MOCK_FETCH, return_value=entries):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is not None


def test_filters_out_zero_both_columns() -> None:
    """Entries with F=0 AND G=0 are excluded from calculation."""
    entries = [
        _entry('AAPL', 0.0, 0.0),
        _entry('TSLA', 1000.0, 800.0),
    ]
    with patch(_MOCK_FETCH, return_value=entries):
        report = get_quarterly_achievement_rate(_TODAY)

    assert report is not None
    assert report.symbols == ['TSLA']
    assert report.rate_pct == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# format_achievement_reply
# ---------------------------------------------------------------------------


def test_format_normal_report() -> None:
    report = QuarterlyAchievementReport(
        rate_pct=72.5,
        total_invested=1450.0,
        total_expected=2000.0,
        symbols=['AAPL', 'TSLA'],
        date_range='2026-04-01 ~ 2026-06-30',
    )
    text = format_achievement_reply(report)

    assert '72.50%' in text
    assert '1,450.00' in text
    assert '2,000.00' in text
    assert 'AAPL' in text
    assert 'TSLA' in text


def test_format_no_data_returns_friendly_message() -> None:
    text = format_achievement_reply(None)
    assert '無投資計畫' in text or '無資料' in text


def test_format_denominator_zero_returns_warning() -> None:
    report = QuarterlyAchievementReport(
        rate_pct=-1.0,
        total_invested=500.0,
        total_expected=0.0,
        symbols=['AAPL'],
        date_range='2026-04-01 ~ 2026-06-30',
    )
    text = format_achievement_reply(report)
    assert '0' in text or '無法計算' in text


def test_format_over_100_percent() -> None:
    report = QuarterlyAchievementReport(
        rate_pct=150.0,
        total_invested=1500.0,
        total_expected=1000.0,
        symbols=['NVDA'],
        date_range='2026-04-01 ~ 2026-06-30',
    )
    text = format_achievement_reply(report)
    assert '150.00%' in text
