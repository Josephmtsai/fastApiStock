"""Tests for the pnl_service module (P&L calculation + MarkdownV2 report)."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.schemas.stock import RichStockData
from fastapistock.services.news_service import SentimentNews
from fastapistock.services.pnl_service import (
    _MSG_LIMIT,
    _calc_holding_pnl,
    _calc_market_today_pnl,
    _fmt_us_today_line,
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


def test_calc_holding_pnl_sums_unrealized() -> None:
    stocks = [
        _make_rich('A', 'TW', unrealized_pnl=30000.0),
        _make_rich('B', 'TW', unrealized_pnl=-5000.0),
    ]
    assert _calc_holding_pnl(stocks) == pytest.approx(25000.0)


def test_calc_holding_pnl_none_values_treated_as_zero() -> None:
    stocks = [
        _make_rich('A', 'TW', unrealized_pnl=10000.0),
        _make_rich('B', 'TW', unrealized_pnl=None),
    ]
    assert _calc_holding_pnl(stocks) == pytest.approx(10000.0)


def test_calc_holding_pnl_empty_returns_zero() -> None:
    assert _calc_holding_pnl([]) == pytest.approx(0.0)


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


def _pe(
    symbol: str, shares: int = 100, avg_cost: float = 80.0, pnl: float = 2000.0
) -> PortfolioEntry:
    return PortfolioEntry(
        symbol=symbol, shares=shares, avg_cost=avg_cost, unrealized_pnl=pnl
    )


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
        mock_pr.fetch_portfolio.return_value = {
            '2330': _pe('2330', shares=1000, pnl=45000.0)
        }
        mock_pr.fetch_portfolio_us.return_value = {
            'AAPL': _pe('AAPL', shares=10, pnl=-800.0)
        }
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    assert isinstance(result, list)
    assert len(result) >= 1
    full = '\n'.join(result)
    assert '2026' in full
    assert '2330' in full
    assert 'AAPL' in full
    # Holding P&L should appear inline in the account overview
    assert '持倉' in full


def test_build_pnl_report_tw_fetch_failure_shows_error() -> None:
    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.side_effect = Exception('sheets down')
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '資料讀取失敗' in full


# ── QA gap coverage: Bug #1 / #2 / #3 ─────────────────────────────────────


def test_build_pnl_report_shows_news_in_digest_section() -> None:
    """AC-2.1 / AC-2.2: news moved out of stock rows into the trailing digest."""
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
        mock_pr.fetch_portfolio.return_value = {'2330': _pe('2330')}
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '今日焦點' in full
    assert '🟢 2330 AI需求強勁' in full
    # Stock detail rows (everything before the digest) must not contain 📰
    before_digest = full.split('📰 *今日焦點*')[0]
    assert '📰' not in before_digest
    assert '正面' not in full  # sentiment label no longer rendered as text


def test_build_pnl_report_digest_orders_tw_before_us() -> None:
    """AC-2.2: digest lists TW holdings before US, with 🟢/🔴 markers."""
    tw_stock = _make_rich('2330', 'TW', shares=100)
    us_stock = _make_rich('AAPL', 'US', shares=10)

    def fake_news(symbol: str, market: str, max_items: int = 2) -> list[SentimentNews]:
        if symbol == '2330':
            return [SentimentNews(title='看好下半年', sentiment='正面')]
        return [SentimentNews(title='銷售下滑', sentiment='負面')]

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch(
            'fastapistock.services.pnl_service.get_sentiment_news',
            side_effect=fake_news,
        ),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': _pe('2330')}
        mock_pr.fetch_portfolio_us.return_value = {'AAPL': _pe('AAPL', shares=10)}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    tw_line = '🟢 2330 看好下半年'
    us_line = '🔴 AAPL 銷售下滑'
    assert tw_line in full
    assert us_line in full
    assert full.index(tw_line) < full.index(us_line)


def test_build_pnl_report_digest_filters_neutral_and_caps_at_two() -> None:
    """AC-2.3: neutral items filtered, then first 2 signal items kept."""
    tw_stock = _make_rich('2330', 'TW', shares=100)
    items = [
        SentimentNews(title='中性一', sentiment='中性'),
        SentimentNews(title='中性二', sentiment='中性'),
        SentimentNews(title='正面三', sentiment='正面'),
        SentimentNews(title='正面四', sentiment='正面'),
        SentimentNews(title='正面五', sentiment='正面'),
    ]

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch(
            'fastapistock.services.pnl_service.get_sentiment_news',
            return_value=items,
        ) as mock_news,
        patch('fastapistock.services.pnl_service.get_usd_twd_rate', return_value=None),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': _pe('2330')}
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '正面三' in full
    assert '正面四' in full
    assert '正面五' not in full
    assert '中性一' not in full
    mock_news.assert_called_with('2330', 'TW', max_items=5)


def test_build_pnl_report_digest_all_neutral_shows_no_highlight() -> None:
    """AC-2.4 / E-8: all-neutral news renders the no-highlight placeholder."""
    tw_stock = _make_rich('2330', 'TW', shares=100)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch(
            'fastapistock.services.pnl_service.get_sentiment_news',
            return_value=[SentimentNews(title='平穩', sentiment='中性')],
        ),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': _pe('2330')}
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '今日無重點新聞' in full
    assert '今日焦點' not in full


def test_build_pnl_report_digest_single_stock_exception_keeps_others() -> None:
    """E-12: one stock's news failure does not hide other stocks' news."""
    tw_a = _make_rich('2330', 'TW', shares=100)
    tw_b = _make_rich('0050', 'TW', shares=100)

    def fake_news(symbol: str, market: str, max_items: int = 2) -> list[SentimentNews]:
        if symbol == '2330':
            raise RuntimeError('news boom')
        return [SentimentNews(title='看好後市', sentiment='正面')]

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch(
            'fastapistock.services.pnl_service.get_sentiment_news',
            side_effect=fake_news,
        ),
    ):
        mock_pr.fetch_portfolio.return_value = {
            '2330': _pe('2330'),
            '0050': _pe('0050'),
        }
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.side_effect = lambda sym: (
            tw_a if sym == '2330' else tw_b
        )
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '🟢 0050 看好後市' in full


def test_build_pnl_report_digest_escapes_markdown_special_chars() -> None:
    """AC-2.5: MarkdownV2 special characters in titles are escaped."""
    tw_stock = _make_rich('2330', 'TW', shares=100)
    news_item = SentimentNews(title='看好 (Q3) 上漲 1.5%', sentiment='正面')

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch(
            'fastapistock.services.pnl_service.get_sentiment_news',
            return_value=[news_item],
        ),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': _pe('2330')}
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '看好 \\(Q3\\) 上漲 1\\.5%' in full


def test_build_pnl_report_us_fetch_failure_shows_error() -> None:
    tw_stock = _make_rich('2330', 'TW', change=10.0, shares=100)
    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.return_value = {'2330': _pe('2330')}
        mock_pr.fetch_portfolio_us.side_effect = Exception('us sheets down')
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '資料讀取失敗' in full
    assert '2330' in full


def test_build_pnl_report_news_exception_shows_no_highlight() -> None:
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
        mock_pr.fetch_portfolio.return_value = {'2330': _pe('2330')}
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = tw_stock
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '今日無重點新聞' in full
    assert '2330' in full


def test_build_pnl_report_one_tw_stock_not_found_still_renders_others() -> None:
    from fastapistock.repositories.twstock_repo import StockNotFoundError

    good_stock = _make_rich('0050', 'TW', shares=100)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.return_value = {
            '2330': _pe('2330'),
            '0050': _pe('0050'),
        }
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.side_effect = lambda sym: (
            good_stock
            if sym == '0050'
            else (_ for _ in ()).throw(StockNotFoundError(sym))
        )
        mock_us.get_us_stocks.return_value = []

        tz = ZoneInfo('Asia/Taipei')
        result = build_pnl_report(datetime(2026, 5, 22, 15, 0, tzinfo=tz))

    full = '\n'.join(result)
    assert '0050' in full
    assert '資料讀取失敗' not in full


def test_build_pnl_report_tw_portfolio_shares_merged_into_rich_data() -> None:
    """get_rich_tw_stock returns shares=None; pnl_service must merge from portfolio."""
    bare_stock = _make_rich(
        '2330', 'TW', shares=None, avg_cost=None, unrealized_pnl=None
    )

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.return_value = {
            '2330': _pe('2330', shares=500, avg_cost=650.0, pnl=12500.0)
        }
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = bare_stock
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    # Stock must appear in report (shares correctly merged from portfolio entry)
    assert '2330' in full
    assert '目前無持股' not in full


# ── 013-3: _fmt_us_today_line unit tests ───────────────────────────────────


def test_fmt_us_today_line_with_rate_contains_twd() -> None:
    # AC-1: rate=32.5, us_today=1257.93 → round(1257.93 * 32.5) = 40883
    result = _fmt_us_today_line(1257.93, 32.5)
    assert '≈NT$' in result
    assert '40,883' in result


def test_fmt_us_today_line_without_rate_matches_fmt_us_amount() -> None:
    # AC-2: rate=None → identical to _fmt_us_amount output
    from fastapistock.services.pnl_service import _fmt_us_amount

    result = _fmt_us_today_line(1257.93, None)
    assert result == _fmt_us_amount(1257.93)
    assert '≈NT$' not in result


def test_fmt_us_today_line_negative_today_with_rate() -> None:
    # AC-3: us_today=-100.0, rate=32.5 → twd=-3250 → '≈NT$-3,250'
    result = _fmt_us_today_line(-100.0, 32.5)
    assert '≈NT$' in result
    assert '-3,250' in result


def test_fmt_us_today_line_zero_today_with_rate() -> None:
    # AC-4: us_today=0.0, rate=32.5 → twd=0 → sign '+', '≈NT$+0' or '≈NT$0'
    result = _fmt_us_today_line(0.0, 32.5)
    assert '≈NT$' in result
    assert '0' in result
    # Sign prefix: twd_amount == 0, so sign='+', formatted as '+0'
    assert '+0' in result


def test_build_pnl_report_includes_twd_when_rate_available() -> None:
    # AC-1 (integration): build_pnl_report embeds TWD conversion in us_line
    us_stock = _make_rich('AAPL', 'US', change=10.0, shares=10, unrealized_pnl=500.0)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
        patch('fastapistock.services.pnl_service.get_usd_twd_rate', return_value=32.5),
    ):
        mock_pr.fetch_portfolio.return_value = {}
        mock_pr.fetch_portfolio_us.return_value = {'AAPL': _pe('AAPL', shares=10)}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.return_value = _make_rich('AAPL', 'TW')
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 6, 13, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '≈NT' in full


def test_build_pnl_report_fallback_when_rate_none() -> None:
    # AC-2 (integration): report still renders without TWD when rate=None
    us_stock = _make_rich('AAPL', 'US', change=10.0, shares=10, unrealized_pnl=500.0)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service'),
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
        patch('fastapistock.services.pnl_service.get_usd_twd_rate', return_value=None),
    ):
        mock_pr.fetch_portfolio.return_value = {}
        mock_pr.fetch_portfolio_us.return_value = {'AAPL': _pe('AAPL', shares=10)}
        mock_pr.fetch_pnl_us.return_value = None
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 6, 13, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '美股今日' in full
    assert '≈NT' not in full


def test_build_pnl_report_rate_exception_does_not_break_report() -> None:
    # AC-5: get_usd_twd_rate raises Exception → report still sent
    us_stock = _make_rich('AAPL', 'US', change=10.0, shares=10, unrealized_pnl=500.0)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service'),
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
        patch(
            'fastapistock.services.pnl_service.get_usd_twd_rate',
            side_effect=RuntimeError('redis down'),
        ),
    ):
        mock_pr.fetch_portfolio.return_value = {}
        mock_pr.fetch_portfolio_us.return_value = {'AAPL': _pe('AAPL', shares=10)}
        mock_pr.fetch_pnl_us.return_value = None
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 6, 13, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)  # must not raise

    full = '\n'.join(result)
    assert '美股今日' in full


def test_build_pnl_report_holding_part_displays_twd() -> None:
    # AC-1: 持倉 column shows TWD value from H21 (fetch_pnl_us)
    us_stock = _make_rich('AAPL', 'US', change=10.0, shares=10, unrealized_pnl=54560.84)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service'),
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
        patch('fastapistock.services.pnl_service.get_usd_twd_rate', return_value=32.5),
    ):
        mock_pr.fetch_portfolio.return_value = {}
        mock_pr.fetch_portfolio_us.return_value = {
            'AAPL': _pe('AAPL', shares=10, pnl=54560.84)
        }
        mock_pr.fetch_pnl_us.return_value = 1_780_231.0
        mock_pr.fetch_pnl_tw.return_value = None
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 6, 13, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert 'NT$1,780,231' in full  # holding shows TWD from H21


def test_build_pnl_report_holding_hidden_when_pnl_us_none() -> None:
    # AC-2: when fetch_pnl_us returns None, holding part is omitted
    us_stock = _make_rich('AAPL', 'US', change=10.0, shares=10, unrealized_pnl=54560.84)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service'),
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
        patch('fastapistock.services.pnl_service.get_usd_twd_rate', return_value=32.5),
    ):
        mock_pr.fetch_portfolio.return_value = {}
        mock_pr.fetch_portfolio_us.return_value = {
            'AAPL': _pe('AAPL', shares=10, pnl=54560.84)
        }
        mock_pr.fetch_pnl_us.return_value = None
        mock_pr.fetch_pnl_tw.return_value = None
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 6, 13, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '美股今日' in full  # report still sends
    # No holding segment when H21 is None
    overview_line = next((ln for ln in full.splitlines() if '美股今日' in ln), '')
    assert '持倉：' not in overview_line


def test_build_pnl_report_holding_hidden_when_fetch_pnl_us_raises() -> None:
    # AC-3: when fetch_pnl_us raises, holding part is omitted and report continues
    us_stock = _make_rich('AAPL', 'US', change=10.0, shares=10, unrealized_pnl=54560.84)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service'),
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
        patch('fastapistock.services.pnl_service.get_usd_twd_rate', return_value=32.5),
    ):
        mock_pr.fetch_portfolio.return_value = {}
        mock_pr.fetch_portfolio_us.return_value = {
            'AAPL': _pe('AAPL', shares=10, pnl=54560.84)
        }
        mock_pr.fetch_pnl_us.side_effect = RuntimeError('network error')
        mock_pr.fetch_pnl_tw.return_value = None
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 6, 13, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)  # must not raise

    full = '\n'.join(result)
    assert '美股今日' in full


# ---------------------------------------------------------------------------
# Extra edge cases (QA additions)
# ---------------------------------------------------------------------------


def test_build_pnl_report_tw_stock_generic_exception_skipped() -> None:
    """When a TW stock fetch raises a generic Exception (not StockNotFoundError),
    that stock is skipped but the rest of the report is still built (lines 263-264)."""
    good_stock = _make_rich('0050', 'TW', shares=100)

    with (
        patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr,
        patch('fastapistock.services.pnl_service.stock_service') as mock_ss,
        patch('fastapistock.services.pnl_service.us_stock_service') as mock_us,
        patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]),
    ):
        mock_pr.fetch_portfolio.return_value = {
            '9999': _pe('9999'),
            '0050': _pe('0050'),
        }
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_pr.fetch_pnl_us.return_value = None
        mock_ss.get_rich_tw_stock.side_effect = lambda sym: (
            good_stock
            if sym == '0050'
            else (_ for _ in ()).throw(ValueError('unexpected error'))
        )
        mock_us.get_us_stocks.return_value = []

        tz = ZoneInfo('Asia/Taipei')
        result = build_pnl_report(datetime(2026, 5, 22, 15, 0, tzinfo=tz))

    full = '\n'.join(result)
    # Good stock still rendered; report not broken
    assert '0050' in full
    assert '資料讀取失敗' not in full


def test_fmt_us_today_line_large_positive_rate_formats_correctly() -> None:
    """Verify thousand-separator formatting for large TWD amounts."""
    # us_today=10000.0, rate=32.5 -> twd=325000 -> '325,000'
    result = _fmt_us_today_line(10000.0, 32.5)
    assert '325,000' in result
    assert '+325,000' in result  # sign prefix applied


def test_fmt_us_today_line_very_small_positive_rounds_to_zero() -> None:
    """us_today close to zero rounds to twd=0 with + prefix."""
    # us_today=0.001, rate=32.5 -> twd=round(0.0325)=0 -> '+0'
    result = _fmt_us_today_line(0.001, 32.5)
    assert '+0' in result
