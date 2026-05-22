"""Tests for the pnl_service module (P&L calculation + MarkdownV2 report)."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from fastapistock.schemas.stock import RichStockData
from fastapistock.services.news_service import SentimentNews
from fastapistock.services.pnl_service import (
    _MSG_LIMIT,
    _calc_market_today_pnl,
    _held_stocks,
    _split_message,
    build_pnl_report,
)


def _make_rich(
    symbol: str,
    market: str,
    price: float = 100.0,
    prev_close: float = 95.0,
    change: float = 5.0,
    change_pct: float = 5.26,
    shares: int | None = 100,
    avg_cost: float | None = 80.0,
    unrealized_pnl: float | None = 2000.0,
) -> RichStockData:
    return RichStockData(
        symbol=symbol,
        display_name=symbol,
        market=market,  # type: ignore[arg-type]
        price=price,
        prev_close=prev_close,
        change=change,
        change_pct=change_pct,
        ma20=90.0,
        volume=1000,
        volume_avg20=900,
        shares=shares,
        avg_cost=avg_cost,
        unrealized_pnl=unrealized_pnl,
    )


# ── T3: Calculation Helpers ─────────────────────────────────────────────────


def test_held_stocks_filters_none_shares() -> None:
    stocks = [
        _make_rich('A', 'TW', shares=100),
        _make_rich('B', 'TW', shares=None),
        _make_rich('C', 'TW', shares=0),
    ]
    result = _held_stocks(stocks)
    assert [s.symbol for s in result] == ['A']


def test_calc_market_today_pnl_sums_change_times_shares() -> None:
    stocks = [
        _make_rich('A', 'TW', change=5.0, shares=200),
        _make_rich('B', 'TW', change=-3.0, shares=100),
    ]
    total = _calc_market_today_pnl(stocks)
    assert total == pytest.approx(5.0 * 200 + (-3.0) * 100)


def test_calc_market_today_pnl_empty_returns_zero() -> None:
    assert _calc_market_today_pnl([]) == pytest.approx(0.0)


# ── T4: Message Formatting ──────────────────────────────────────────────────


def test_split_message_short_message_not_split() -> None:
    msg = 'Hello world'
    assert _split_message(msg) == ['Hello world']


def test_split_message_long_message_splits_at_newline() -> None:
    line = 'A' * 100 + '\n'
    msg = line * 50  # 5050 chars > 4096
    parts = _split_message(msg)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= _MSG_LIMIT


def test_build_pnl_report_returns_list_of_strings() -> None:
    tw_stock = _make_rich(
        '2330', 'TW', change=15.0, shares=1000, unrealized_pnl=45000.0
    )
    us_stock = _make_rich('AAPL', 'US', change=-3.2, shares=10, unrealized_pnl=-800.0)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': MagicMock()}
        mock_pr.fetch_portfolio_us.return_value = {'AAPL': MagicMock()}
        mock_ss.get_rich_tw_stocks.return_value = [tw_stock]
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    assert isinstance(result, list)
    assert len(result) >= 1
    full = '\n'.join(result)
    assert '2026' in full
    assert '2330' in full
    assert 'AAPL' in full


def test_build_pnl_report_tw_fetch_failure_shows_error() -> None:
    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.side_effect = Exception('sheets down')
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '資料讀取失敗' in full


# ── QA gap coverage: Bug #1 / #2 / #3 ─────────────────────────────────────


def test_build_pnl_report_shows_news_in_stock_row() -> None:
    tw_stock = _make_rich('2330', 'TW', shares=100)
    news_item = SentimentNews(title='AI需求強勁', sentiment='正面')

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch(
            'fastapistock.services.pnl_service.get_sentiment_news',
            return_value=[news_item],
        ),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': MagicMock()}
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_ss.get_rich_tw_stocks.return_value = [tw_stock]
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '📰' in full
    assert '正面' in full


def test_build_pnl_report_us_fetch_failure_shows_error() -> None:
    tw_stock = _make_rich('2330', 'TW', change=10.0, shares=100)
    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': MagicMock()}
        mock_pr.fetch_portfolio_us.side_effect = Exception('us sheets down')
        mock_ss.get_rich_tw_stocks.return_value = [tw_stock]
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '資料讀取失敗' in full
    assert '2330' in full


def test_build_pnl_report_news_exception_shows_no_news() -> None:
    tw_stock = _make_rich('2330', 'TW', shares=100)
    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch(
            'fastapistock.services.pnl_service.get_sentiment_news',
            side_effect=RuntimeError('news boom'),
        ),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': MagicMock()}
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_ss.get_rich_tw_stocks.return_value = [tw_stock]
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '暫無新聞' in full
    assert '2330' in full
