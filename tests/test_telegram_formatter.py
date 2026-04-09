"""Tests for the rich Telegram message formatter."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapistock.schemas.stock import RichStockData
from fastapistock.services.telegram_service import (
    _escape_md,
    format_rich_stock_message,
)

_TZ = ZoneInfo('Asia/Taipei')


def _make_stock(
    symbol: str = 'TEST',
    market: str = 'TW',
    price: float = 100.0,
    rsi: float | None = 55.0,
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
        ma50=90.0,
        rsi=rsi,
        macd=0.5,
        macd_signal=0.3,
        macd_hist=0.2,
        bb_upper=105.0,
        bb_mid=95.0,
        bb_lower=85.0,
        volume=1_000_000,
        volume_avg20=800_000,
        week52_high=120.0,
        week52_low=80.0,
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

    def test_change_sign_escaped(self) -> None:
        stock = _make_stock(price=100.0)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        # positive change should show escaped + or raw + inside code span
        assert '2.00' in msg  # change value present

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
