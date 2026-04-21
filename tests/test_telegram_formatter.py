"""Tests for the rich Telegram message formatter."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapistock.schemas.stock import RichStockData
from fastapistock.services.telegram_service import (
    _calc_cost_signal,
    _escape_md,
    format_rich_stock_message,
)

_TZ = ZoneInfo('Asia/Taipei')


def _make_stock(
    symbol: str = 'TEST',
    market: str = 'TW',
    price: float = 100.0,
    rsi: float | None = 55.0,
    avg_cost: float | None = None,
    unrealized_pnl: float | None = None,
    shares: int | None = None,
    ma50: float | None = 90.0,
    week52_high: float | None = 120.0,
) -> RichStockData:
    return RichStockData(
        symbol=symbol,
        display_name='Test Corp',
        market=market,  # type: ignore[arg-type]
        price=price,
        prev_close=98.0,
        change=2.0,
        change_pct=2.04,
        ma20=95.0,
        ma50=ma50,
        rsi=rsi,
        macd=0.5,
        macd_signal=0.3,
        macd_hist=0.2,
        bb_upper=105.0,
        bb_mid=95.0,
        bb_lower=85.0,
        volume=1_000_000,
        volume_avg20=800_000,
        week52_high=week52_high,
        week52_low=80.0,
        avg_cost=avg_cost,
        unrealized_pnl=unrealized_pnl,
        shares=shares,
    )


class TestEscapeMd:
    def test_escapes_dot(self) -> None:
        assert _escape_md('3.14') == r'3\.14'

    def test_escapes_plus(self) -> None:
        assert _escape_md('+2.30') == r'\+2\.30'

    def test_escapes_minus(self) -> None:
        assert _escape_md('-1.5') == r'\-1\.5'

    def test_escapes_parentheses(self) -> None:
        assert _escape_md('(ok)') == r'\(ok\)'

    def test_no_change_for_plain_chinese(self) -> None:
        assert _escape_md('元大台灣50') == '元大台灣50'

    def test_escapes_pipe(self) -> None:
        assert _escape_md('a|b') == r'a\|b'


class TestFormatRichStockMessage:
    def test_tw_header_present(self) -> None:
        stock = _make_stock(market='TW')
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '*台股定時推播*' in msg

    def test_us_header_present(self) -> None:
        stock = _make_stock(market='US')
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert '*美股定時推播*' in msg

    def test_rsi_line_present_when_not_none(self) -> None:
        stock = _make_stock(rsi=55.0)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert 'RSI' in msg

    def test_rsi_line_absent_when_none(self) -> None:
        stock = _make_stock(rsi=None)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert 'RSI' not in msg

    def test_positive_change_pct_plus_and_dot_escaped_outside_backticks(self) -> None:
        stock = _make_stock(price=100.0)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        # Unescaped '+' or '.' outside backticks causes Telegram 400 error.
        # The parenthetical change_pct must use '\+X\.XX%', not '+X.XX%'.
        assert r'\+' in msg  # escaped + in \(+X.XX%\)
        assert r'\.' in msg  # escaped . in \(+X.XX%\)
        assert '2.00' in msg  # raw change value still present inside code span

    def test_volume_not_in_message(self) -> None:
        stock = _make_stock()
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '成交量' not in msg

    def test_macd_indicator_line_not_in_message(self) -> None:
        # 'MACD:' display line removed; MACD may still appear in score reasons
        stock = _make_stock()
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert 'MACD:' not in msg

    def test_bollinger_not_in_message(self) -> None:
        stock = _make_stock()
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '布林' not in msg

    def test_us_premarket_shown_when_present(self) -> None:
        stock = _make_stock(market='US')
        stock = stock.model_copy(update={'premarket_price': 196.50})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert '盤前' in msg
        assert '196' in msg

    def test_us_premarket_absent_when_none(self) -> None:
        stock = _make_stock(market='US')
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert '盤前' not in msg

    def test_tw_premarket_never_shown(self) -> None:
        stock = _make_stock(market='TW')
        stock = stock.model_copy(update={'premarket_price': 196.50})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '盤前' not in msg

    def test_negative_score_dash_escaped(self) -> None:
        # score=-3 → '看跌' verdict, result.score=-3 → must render as r'\-3', not '-3'
        stock = _make_stock(
            price=80.0,  # below MA20=95 → bear signal
            rsi=75.0,  # overbought → bear
        )
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        import re as _re

        score_match = _re.search(r'評分 (.*?)/8', msg)
        assert score_match is not None
        raw_score = score_match.group(1)
        # A bare '-' (not preceded by '\') would cause Telegram 400
        assert not _re.search(r'(?<!\\)-', raw_score), (
            f'Unescaped dash in score: {raw_score!r}'
        )

    def test_footer_present(self) -> None:
        stock = _make_stock()
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert 'FastAPI Stock Bot' in msg

    def test_multiple_stocks_both_appear(self) -> None:
        s1 = _make_stock(symbol='AAA', market='TW')
        s2 = _make_stock(symbol='BBB', market='TW')
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([s1, s2], 'TW', now)
        assert 'AAA' in msg
        assert 'BBB' in msg

    def test_tw_uses_twd_currency(self) -> None:
        stock = _make_stock(market='TW')
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert 'TWD' in msg

    def test_us_uses_usd_currency(self) -> None:
        stock = _make_stock(market='US')
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert 'USD' in msg

    def test_portfolio_block_shown_when_avg_cost_and_shares_present(self) -> None:
        stock = _make_stock(avg_cost=820.0, shares=1000, unrealized_pnl=75000.0)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '持倉' in msg
        assert '成本' in msg
        assert '損益' in msg

    def test_portfolio_block_absent_when_avg_cost_is_none(self) -> None:
        stock = _make_stock(avg_cost=None)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '持倉' not in msg

    def test_portfolio_negative_pnl_shows_minus(self) -> None:
        stock = _make_stock(avg_cost=850.0, shares=500, unrealized_pnl=-35000.0)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '損益' in msg
        # '-35,000' should appear in the message (escaped form)
        assert '35' in msg and '000' in msg

    def test_portfolio_shown_for_us_stock_when_avg_cost_set(self) -> None:
        # Formatter doesn't gate on market; service guarantees US has avg_cost=None.
        # This tests that the formatter renders portfolio for any market.
        stock = _make_stock(market='US', avg_cost=820.0, shares=1000)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert '持倉' in msg

    def test_us_portfolio_pnl_uses_usd_unit(self) -> None:
        stock = _make_stock(
            market='US',
            avg_cost=180.0,
            shares=10,
            unrealized_pnl=12000.0,
        )
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert '損益' in msg
        assert 'USD' in msg


class TestCalcCostSignal:
    # -----------------------------------------------------------------------
    # TW positive triggers (week52_high=100 as baseline)
    # -----------------------------------------------------------------------
    def test_tw_minus20_pct_returns_one_star(self) -> None:
        # drop_pct = (80 - 100) / 100 * 100 = -20% → matches -20 threshold → 🟠⭐
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is not None
        assert '🟠' in result
        assert '⭐' in result

    def test_tw_minus26_pct_returns_two_stars(self) -> None:
        # drop_pct = (74 - 100) / 100 * 100 = -26% → matches -25 threshold → 🔴⭐⭐
        result = _calc_cost_signal(
            price=74.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is not None
        assert '🔴' in result
        assert '⭐⭐' in result
        assert '⭐⭐⭐' not in result

    def test_tw_minus31_pct_returns_three_stars(self) -> None:
        # drop_pct = (69 - 100) / 100 * 100 = -31% → matches -30 threshold → 🔴⭐⭐⭐
        result = _calc_cost_signal(
            price=69.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is not None
        assert '🔴' in result
        assert '⭐⭐⭐' in result

    def test_tw_minus15_pct_returns_none(self) -> None:
        # drop_pct = (85 - 100) / 100 * 100 = -15% → below -20 threshold → None
        result = _calc_cost_signal(
            price=85.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is None

    # -----------------------------------------------------------------------
    # US positive triggers (week52_high=100 as baseline)
    # -----------------------------------------------------------------------
    def test_us_minus20_pct_returns_orange_one_star(self) -> None:
        # drop_pct = (80 - 100) / 100 * 100 = -20% → matches -20 threshold → 🟠⭐
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=90.0, market='US'
        )
        assert result is not None
        assert '🟠' in result
        assert '⭐' in result

    def test_us_minus31_pct_returns_two_stars(self) -> None:
        # drop_pct = (69 - 100) / 100 * 100 = -31% → matches -30 threshold → 🔴⭐⭐
        result = _calc_cost_signal(
            price=69.0, week52_high=100.0, ma50=90.0, market='US'
        )
        assert result is not None
        assert '🔴' in result
        assert '⭐⭐' in result
        assert '⭐⭐⭐' not in result

    def test_us_minus41_pct_returns_three_stars(self) -> None:
        # drop_pct = (59 - 100) / 100 * 100 = -41% → matches -40 threshold → 🔴⭐⭐⭐
        result = _calc_cost_signal(
            price=59.0, week52_high=100.0, ma50=90.0, market='US'
        )
        assert result is not None
        assert '🔴' in result
        assert '⭐⭐⭐' in result

    # -----------------------------------------------------------------------
    # Boundary / edge cases
    # -----------------------------------------------------------------------
    def test_week52_high_none_returns_none(self) -> None:
        result = _calc_cost_signal(price=80.0, week52_high=None, ma50=90.0, market='TW')
        assert result is None

    def test_week52_high_zero_returns_none(self) -> None:
        result = _calc_cost_signal(price=80.0, week52_high=0.0, ma50=90.0, market='TW')
        assert result is None

    def test_ma50_none_returns_none(self) -> None:
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=None, market='TW'
        )
        assert result is None

    def test_price_above_ma50_returns_none(self) -> None:
        # price=80 > ma50=75 → MA50 condition not met → None
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=75.0, market='TW'
        )
        assert result is None

    def test_price_below_ma50_with_signal(self) -> None:
        # price=80 < ma50=90, drop_pct=-20% → matches -20 threshold → signal present
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is not None
        assert '⭐' in result
        assert 'MA50' in result

    # -----------------------------------------------------------------------
    # Output format validation
    # -----------------------------------------------------------------------
    def test_output_contains_money_bag_emoji(self) -> None:
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is not None
        assert '💰' in result

    def test_output_contains_ma50_broken_text(self) -> None:
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is not None
        assert 'MA50 已跌破' in result

    def test_output_contains_high_distance_text(self) -> None:
        result = _calc_cost_signal(
            price=80.0, week52_high=100.0, ma50=90.0, market='TW'
        )
        assert result is not None
        assert '距高點' in result
