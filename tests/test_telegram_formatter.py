"""Tests for the rich Telegram message formatter."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapistock.schemas.stock import RichStockData
from fastapistock.services.telegram_service import (
    _build_indicator_summary,
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

    def test_bearish_verdict_uses_down_chart_emoji_and_escaped_score(self) -> None:
        # score <= -3 → '偏看跌' verdict → 📉 emoji; negative score renders r'\-4'
        stock = _make_stock(price=80.0, rsi=75.0, ma50=95.0).model_copy(
            update={
                'macd_hist': -0.5,
                'change': -3.0,
                'change_pct': -3.6,
                'bb_upper': 105.0,
                'bb_lower': 85.0,
            }
        )
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '📉' in msg
        assert '看跌' in msg
        assert r'評分 \-4/8' in msg

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
        assert '35' in msg and '000' in msg

    def test_cost_and_pnl_inside_code_span_have_no_backslash(self) -> None:
        # Inside MarkdownV2 code spans, backslash is a literal character.
        # _escape_md must NOT be applied to values placed inside backticks,
        # otherwise '1298.98' renders as '1298\.98' with a visible backslash.
        import re

        stock = _make_stock(avg_cost=1298.98, shares=3058, unrealized_pnl=3_181_693.0)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)

        # Extract every code-span content (text between backticks)
        code_spans = re.findall(r'`([^`]+)`', msg)
        for span in code_spans:
            assert '\\' not in span, f'Backslash found inside code span: {span!r}'

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


class TestPreMarketDisplay:
    """US pre-market display flips line 2/3 to show live pre-market price."""

    def test_premarket_price_shown_on_line_2_with_tag(self) -> None:
        stock = _make_stock(market='US', price=387.44)
        stock = stock.model_copy(update={'premarket_price': 383.32})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        # Pre-market price appears as 最後成交
        assert '383.32 USD' in msg
        # Escaped [盤前] tag visible in MarkdownV2
        assert r'\[盤前\]' in msg
        # 昨收 uses regular-session close (stock.price)
        assert '昨收: `387.44`' in msg

    def test_premarket_change_reflects_pm_vs_prev_close(self) -> None:
        # pm_change = 383.32 - 387.44 = -4.12
        # pm_pct = -4.12 / 387.44 * 100 ≈ -1.0634 → -1.06%
        stock = _make_stock(market='US', price=387.44)
        stock = stock.model_copy(update={'premarket_price': 383.32})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        # Raw change inside backticks is unescaped
        assert '-4.12' in msg
        # pct appears in the parenthetical with escaped dot
        assert r'1\.06' in msg

    def test_premarket_no_legacy_premarket_line(self) -> None:
        # Legacy output had '盤前: <price> USD  (+X.XX%)' on its own line.
        # New layout merges it into line 2 — that legacy line must be gone.
        stock = _make_stock(market='US', price=387.44)
        stock = stock.model_copy(update={'premarket_price': 383.32})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        # The literal '盤前: `' prefix from the old dedicated line
        assert '盤前: `' not in msg

    def test_us_without_premarket_uses_legacy_layout(self) -> None:
        stock = _make_stock(market='US', price=387.44)
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        # No [盤前] tag when premarket_price is None
        assert r'\[盤前\]' not in msg
        # Legacy '前收' label for US regular session
        assert '前收' in msg
        assert '昨收' not in msg

    def test_tw_never_uses_premarket_layout(self) -> None:
        # Even if premarket_price were somehow set for TW, market check blocks it.
        stock = _make_stock(market='TW', price=100.0)
        stock = stock.model_copy(update={'premarket_price': 95.0})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert r'\[盤前\]' not in msg
        # TW still uses its own '昨收' label, but no pre-market tag
        assert '昨收' in msg

    def test_premarket_negative_direction_shows_minus(self) -> None:
        # premarket (383.32) < price (387.44) → change negative
        stock = _make_stock(market='US', price=387.44)
        stock = stock.model_copy(update={'premarket_price': 383.32})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        # Raw value '-4.12' sits inside backticks (unescaped)
        assert '-4.12' in msg
        # Escaped negative pct in the parenthetical
        assert r'\-1\.06' in msg

    def test_premarket_positive_direction_shows_plus(self) -> None:
        # premarket (200.00) > price (180.00) → change positive
        stock = _make_stock(market='US', price=180.0)
        stock = stock.model_copy(update={'premarket_price': 200.0})
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert '+20.00' in msg
        # pm_pct = 20 / 180 * 100 ≈ 11.11%
        assert r'\+11\.11' in msg


def _summary_stock(**overrides: float | int | None) -> RichStockData:
    """Build a RichStockData with field overrides for summary-line tests."""
    return _make_stock().model_copy(update=dict(overrides))


def _full_indicator_stock() -> RichStockData:
    """Stock matching AC-1.1: all five summary segments present."""
    return _summary_stock(
        price=100.0,
        rsi=72.0,
        macd_hist=0.2,
        ma20=95.0,
        ma50=90.0,
        bb_upper=101.0,
        bb_lower=85.0,
        volume=1_800_000,
        volume_avg20=1_000_000,
    )


class TestIndicatorSummaryLine:
    """Spec 016: single-line symbol summary replacing RSI/MA/reason lines."""

    # -- AC-1.1: all segments present, order and format ----------------------
    def test_full_summary_all_segments(self) -> None:
        summary = _build_indicator_summary(_full_indicator_stock())
        assert summary == 'RSI 72⚠️ │ MACD ✚ │ MA20↑ MA50↑ │ BB 高檔 │ 量 1.8x'

    def test_full_summary_escaped_in_message(self) -> None:
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([_full_indicator_stock()], 'TW', now)
        assert 'RSI 72⚠️ │ MACD ✚ │ MA20↑ MA50↑ │ BB 高檔 │ 量 1\\.8x' in msg

    # -- AC-1.2 / AC-1.3 / E9: RSI warning threshold -------------------------
    def test_rsi_55_no_warning(self) -> None:
        summary = _build_indicator_summary(_summary_stock(rsi=55.0))
        assert summary is not None
        assert 'RSI 55' in summary
        assert '⚠️' not in summary

    def test_rsi_70_has_warning(self) -> None:
        summary = _build_indicator_summary(_summary_stock(rsi=70.0))
        assert summary is not None
        assert 'RSI 70⚠️' in summary

    def test_rsi_30_has_warning(self) -> None:
        summary = _build_indicator_summary(_summary_stock(rsi=30.0))
        assert summary is not None
        assert 'RSI 30⚠️' in summary

    def test_rsi_none_segment_omitted(self) -> None:
        summary = _build_indicator_summary(_summary_stock(rsi=None))
        assert summary is not None
        assert 'RSI' not in summary

    # -- AC-1.4 / E3: MACD symbol -------------------------------------------
    def test_macd_hist_negative_uses_u2500(self) -> None:
        summary = _build_indicator_summary(_summary_stock(macd_hist=-0.3))
        assert summary is not None
        assert 'MACD ─' in summary

    def test_macd_hist_zero_segment_omitted(self) -> None:
        summary = _build_indicator_summary(_summary_stock(macd_hist=0.0))
        assert summary is not None
        assert 'MACD' not in summary

    def test_macd_hist_none_segment_omitted(self) -> None:
        summary = _build_indicator_summary(_summary_stock(macd_hist=None))
        assert summary is not None
        assert 'MACD' not in summary

    # -- AC-1.5: MA arrows ----------------------------------------------------
    def test_ma_arrows_up_and_down(self) -> None:
        summary = _build_indicator_summary(
            _summary_stock(price=92.0, ma20=95.0, ma50=90.0)
        )
        assert summary is not None
        assert 'MA20↓ MA50↑' in summary

    def test_ma50_none_only_ma20_shown(self) -> None:
        summary = _build_indicator_summary(_summary_stock(ma50=None))
        assert summary is not None
        assert 'MA20↑' in summary
        assert 'MA50' not in summary

    # -- AC-1.6 / E4 / E5: Bollinger position --------------------------------
    def test_bb_high_zone(self) -> None:
        summary = _build_indicator_summary(
            _summary_stock(price=100.0, bb_upper=101.0, bb_lower=85.0)
        )
        assert summary is not None
        assert 'BB 高檔' in summary

    def test_bb_low_zone(self) -> None:
        summary = _build_indicator_summary(
            _summary_stock(price=86.0, bb_upper=105.0, bb_lower=85.0)
        )
        assert summary is not None
        assert 'BB 低檔' in summary

    def test_bb_middle_zone_omitted(self) -> None:
        # bb_pos = (100 - 85) / (105 - 85) = 0.75 → segment omitted
        summary = _build_indicator_summary(
            _summary_stock(price=100.0, bb_upper=105.0, bb_lower=85.0)
        )
        assert summary is not None
        assert 'BB' not in summary

    def test_bb_zero_range_omitted_no_error(self) -> None:
        summary = _build_indicator_summary(
            _summary_stock(bb_upper=100.0, bb_lower=100.0)
        )
        assert summary is not None
        assert 'BB' not in summary

    def test_bb_negative_range_omitted_no_error(self) -> None:
        # Malformed data (upper < lower) must not raise nor emit a BB segment.
        summary = _build_indicator_summary(
            _summary_stock(bb_upper=90.0, bb_lower=100.0)
        )
        assert summary is not None
        assert 'BB' not in summary

    def test_bb_pos_exact_085_boundary_omitted(self) -> None:
        # bb_pos = (102 - 85) / (105 - 85) = 0.85 exactly → strict '>' → omitted
        summary = _build_indicator_summary(
            _summary_stock(price=102.0, bb_upper=105.0, bb_lower=85.0)
        )
        assert summary is not None
        assert 'BB' not in summary

    def test_bb_pos_exact_015_boundary_omitted(self) -> None:
        # bb_pos = (88 - 85) / (105 - 85) = 0.15 exactly → strict '<' → omitted
        summary = _build_indicator_summary(
            _summary_stock(price=88.0, bb_upper=105.0, bb_lower=85.0)
        )
        assert summary is not None
        assert 'BB' not in summary

    # -- AC-1.7 / E6: volume ratio --------------------------------------------
    def test_volume_ratio_format(self) -> None:
        summary = _build_indicator_summary(
            _summary_stock(volume=1_800_000, volume_avg20=1_000_000)
        )
        assert summary is not None
        assert '量 1.8x' in summary

    def test_volume_avg20_zero_omitted_no_error(self) -> None:
        summary = _build_indicator_summary(_summary_stock(volume_avg20=0))
        assert summary is not None
        assert '量' not in summary

    def test_volume_zero_omitted(self) -> None:
        summary = _build_indicator_summary(_summary_stock(volume=0))
        assert summary is not None
        assert '量' not in summary

    def test_negative_volume_omitted_no_error(self) -> None:
        # Defensive: schema does not forbid negatives; guard is strict '> 0'.
        summary = _build_indicator_summary(_summary_stock(volume=-5))
        assert summary is not None
        assert '量' not in summary

    def test_negative_volume_avg20_omitted_no_error(self) -> None:
        summary = _build_indicator_summary(_summary_stock(volume_avg20=-5))
        assert summary is not None
        assert '量' not in summary

    def test_extreme_volume_ratio_no_crash_and_escaped(self) -> None:
        # ratio = 10**12 / 1 → '量 1000000000000.0x'; '.' must be escaped in msg
        stock = _summary_stock(volume=10**12, volume_avg20=1)
        summary = _build_indicator_summary(stock)
        assert summary is not None
        assert '量 1000000000000.0x' in summary
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '量 1000000000000\\.0x' in msg

    # -- E1: all indicators missing → no summary line -------------------------
    def test_all_indicators_missing_returns_none(self) -> None:
        stock = _summary_stock(
            rsi=None,
            macd_hist=None,
            ma20=None,
            ma50=None,
            bb_upper=None,
            bb_lower=None,
            volume=0,
            volume_avg20=0,
        )
        assert _build_indicator_summary(stock) is None

    def test_all_indicators_missing_message_has_no_separator(self) -> None:
        stock = _summary_stock(
            rsi=None,
            macd_hist=None,
            ma20=None,
            ma50=None,
            bb_upper=None,
            bb_lower=None,
            volume=0,
            volume_avg20=0,
        )
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '│' not in msg

    # -- E2: partial segments, separator count = segments - 1 ------------------
    def test_partial_segments_separator_count(self) -> None:
        stock = _summary_stock(
            rsi=55.0,
            macd_hist=None,
            ma20=95.0,
            ma50=None,
            bb_upper=None,
            bb_lower=None,
            volume=0,
            volume_avg20=0,
        )
        summary = _build_indicator_summary(stock)
        assert summary == 'RSI 55 │ MA20↑'
        assert summary.count('│') == 1
        assert not summary.startswith('│')
        assert not summary.endswith('│')

    # -- AC-4.1 / AC-4.2 / E8: MarkdownV2 safety ------------------------------
    def test_summary_line_markdown_safe(self) -> None:
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([_full_indicator_stock()], 'TW', now)
        summary_lines = [line for line in msg.split('\n') if '│' in line]
        assert len(summary_lines) == 1
        line = summary_lines[0]
        assert '量 1\\.8x' in line
        for forbidden in ('-', '+', '|'):
            assert forbidden not in line

    # -- AC-2.1 ~ AC-2.3: bloated blocks removed ------------------------------
    def test_old_format_lines_removed(self) -> None:
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([_full_indicator_stock()], 'TW', now)
        assert 'RSI\\(14\\)' not in msg
        assert '均線:' not in msg
        assert '✅' not in msg
        assert '❌' not in msg

    # -- AC-3.1 / E7 / E10: existing blocks preserved --------------------------
    def test_portfolio_and_range_and_score_preserved(self) -> None:
        stock = _full_indicator_stock().model_copy(
            update={'avg_cost': 90.0, 'shares': 1000, 'unrealized_pnl': 10000.0}
        )
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'TW', now)
        assert '持倉' in msg
        assert '近期區間' in msg
        assert '評分' in msg
        assert '│' in msg

    def test_no_position_summary_still_present(self) -> None:
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([_full_indicator_stock()], 'TW', now)
        assert '持倉' not in msg
        assert '│' in msg

    def test_premarket_and_summary_coexist(self) -> None:
        stock = _full_indicator_stock().model_copy(
            update={'market': 'US', 'premarket_price': 105.0}
        )
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([stock], 'US', now)
        assert '盤前' in msg
        assert '│' in msg

    # -- AC-5.1 / AC-5.2: footer legend ----------------------------------------
    def test_footer_legend_present_once(self) -> None:
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message([_full_indicator_stock()], 'TW', now)
        legend = '_✚金叉 ─死叉 ↑站上均線 ↓跌破均線 ⚠️超買/超賣_'
        assert msg.count(legend) == 1

    def test_footer_legend_once_for_multiple_stocks(self) -> None:
        stocks = [_full_indicator_stock(), _full_indicator_stock()]
        now = datetime(2026, 4, 9, 9, 0, tzinfo=_TZ)
        msg = format_rich_stock_message(stocks, 'TW', now)
        assert msg.count('✚金叉') == 1


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
