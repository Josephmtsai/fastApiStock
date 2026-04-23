"""Telegram notification service.

Sends formatted stock information to a Telegram user via the Bot API.
Provides both a simple plain-text sender (send_stock_message) and a rich
MarkdownV2 sender (send_rich_stock_message) with full technical indicators.
"""

import logging
import math
import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from fastapistock.config import TELEGRAM_TOKEN
from fastapistock.repositories import signal_history_repo
from fastapistock.repositories.signal_history_repo import SignalRecord
from fastapistock.schemas.stock import RichStockData, StockData
from fastapistock.services.indicators import IndicatorResult, score_stock

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = 'https://api.telegram.org'
_REQUEST_TIMEOUT = 10

_MD_SPECIAL = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')

# Cost level signal thresholds: (pnl_pct_threshold, color_emoji, star_emoji)
# Sorted from most severe to least — first match wins.
_TW_SIGNAL_THRESHOLDS: list[tuple[float, str, str]] = [
    (-30.0, '🔴', '⭐⭐⭐'),
    (-25.0, '🔴', '⭐⭐'),
    (-20.0, '🟠', '⭐'),
]
_US_SIGNAL_THRESHOLDS: list[tuple[float, str, str]] = [
    (-40.0, '🔴', '⭐⭐⭐'),
    (-30.0, '🔴', '⭐⭐'),
    (-20.0, '🟠', '⭐'),
]


def _escape_md(text: str) -> str:
    """Escape all MarkdownV2 special characters in text.

    Args:
        text: Raw string that may contain MarkdownV2-reserved characters.

    Returns:
        String safe for use outside code/bold/italic spans in MarkdownV2.
    """
    return _MD_SPECIAL.sub(r'\\\1', str(text))


def _format_stock_message(stocks: list[StockData]) -> str:
    """Build the Telegram message text for a list of stocks.

    Args:
        stocks: Non-empty list of StockData instances.

    Returns:
        Newline-delimited message string, one block per stock.
    """
    blocks: list[str] = []
    for s in stocks:
        block = (
            f'股票名稱: {s.ChineseName}\n'
            f'最後成交: {s.price}\n'
            f'月均價: {s.ma20}\n'
            f'季均價: {s.ma60}\n'
            f'昨天收: {s.LastDayPrice}\n'
            f'成交量: {s.Volume}'
        )
        blocks.append(block)
    return '\n\n'.join(blocks)


def send_stock_message(user_id: str, stocks: list[StockData]) -> bool:
    """Send stock information to a Telegram user.

    Args:
        user_id: Telegram chat/user ID to send the message to.
        stocks: List of StockData to include in the message.
            Must be non-empty; callers are responsible for filtering.

    Returns:
        True if the message was delivered successfully, False otherwise.
    """
    if not TELEGRAM_TOKEN:
        logger.error('TELEGRAM_TOKEN is not configured')
        return False

    text = _format_stock_message(stocks)
    url = f'{_TELEGRAM_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': user_id, 'text': text}

    try:
        response = httpx.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info('Telegram message sent to user_id=%s', user_id)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            'Telegram API error for user_id=%s: %s %s',
            user_id,
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except httpx.RequestError as exc:
        logger.error('Telegram request failed for user_id=%s: %s', user_id, exc)
        return False


_STARS_TO_TIER: dict[str, int] = {
    '⭐': 1,
    '⭐⭐': 2,
    '⭐⭐⭐': 3,
}


def _persist_signal(
    symbol: str,
    market: str,
    stars: str,
    drop_pct: float,
    price: float,
    week52_high: float,
    ma50: float,
) -> None:
    """Write the signal to Redis via signal_history_repo (best-effort).

    Any exception is caught and logged so the push pipeline is never disrupted.
    """
    tier = _STARS_TO_TIER.get(stars)
    if tier is None:
        logger.warning('Unknown star pattern %r, skip persist', stars)
        return
    try:
        record = SignalRecord(
            symbol=symbol,
            market=market,
            tier=tier,
            drop_pct=drop_pct,
            price=price,
            week52_high=week52_high,
            ma50=ma50,
            timestamp=datetime.now(ZoneInfo('Asia/Taipei')),
        )
        signal_history_repo.save_signal(record)
    except Exception as exc:
        logger.warning('Persist signal failed for %s/%s: %s', market, symbol, exc)


def _calc_cost_signal(
    price: float,
    week52_high: float | None,
    ma50: float | None,
    market: str,
    symbol: str = '',
) -> str | None:
    """Calculate the 52-week-high drawdown add-on signal line, or None when no signal.

    Args:
        price: Current stock price.
        week52_high: 52-week high price; None or 0 means data unavailable.
        ma50: 50-day moving average; None means condition not met.
        market: 'TW' or 'US'.
        symbol: Stock symbol used for history persistence. When empty, no
            history record is written (useful in tests that only check format).

    Returns:
        Formatted MarkdownV2 signal line string, or None when conditions not met.
    """
    if week52_high is None or week52_high == 0:
        return None

    drop_pct = (price - week52_high) / week52_high * 100

    if not math.isfinite(drop_pct):
        logger.warning('_calc_cost_signal: non-finite drop_pct=%s', drop_pct)
        return None

    if ma50 is None or price >= ma50:
        return None

    thresholds = _TW_SIGNAL_THRESHOLDS if market == 'TW' else _US_SIGNAL_THRESHOLDS
    matched: tuple[float, str, str] | None = None
    for threshold, color, stars in thresholds:
        if drop_pct <= threshold:
            matched = (threshold, color, stars)
            break

    if matched is None:
        return None

    _, color, stars = matched

    if symbol:
        _persist_signal(
            symbol=symbol,
            market=market,
            stars=stars,
            drop_pct=drop_pct,
            price=price,
            week52_high=week52_high,
            ma50=ma50,
        )

    drop_esc = _escape_md(f'{drop_pct:.1f}')
    pipe_esc = _escape_md('|')
    return (
        f'   💰 加碼訊號 {color} {stars}  距高點 {drop_esc}%  {pipe_esc}  MA50 已跌破'
    )


def _build_price_change_lines(stock: RichStockData, currency: str) -> tuple[str, str]:
    """Build the price and change lines, adjusting for US pre-market state.

    During US pre-market, `最後成交` shows the live pre-market price tagged with
    `[盤前]` and `昨收` is the regular-session close (i.e. stock.price). Change
    is computed against that close. All other cases keep the original layout.

    Args:
        stock: RichStockData with market, price, prev_close, change fields.
        currency: Pre-resolved currency label ('TWD' or 'USD').

    Returns:
        Tuple of (price_line, change_line) MarkdownV2 strings.
    """
    if stock.market == 'US' and stock.premarket_price is not None:
        pm_price = stock.premarket_price
        pm_change = pm_price - stock.price
        pm_sign = '+' if pm_change >= 0 else ''
        pm_pct = (pm_change / stock.price * 100) if stock.price else 0.0
        pm_pct_esc = _escape_md(f'{pm_sign}{pm_pct:.2f}')
        pm_tag = _escape_md(' [盤前]')
        price_line = (
            f'   最後成交: `{pm_price:.2f} {currency}`{pm_tag}'
            f'   昨收: `{stock.price:.2f}`'
        )
        change_line = f'   漲跌: `{pm_sign}{pm_change:.2f}` \\({pm_pct_esc}%\\)'
        return price_line, change_line

    sign = '+' if stock.change >= 0 else ''
    # Use :+.2f to include the sign, then escape both '+'/'-' and '.'
    pct_esc = _escape_md(f'{stock.change_pct:+.2f}')
    prev_label = '昨收' if stock.market == 'TW' else '前收'
    price_line = (
        f'   最後成交: `{stock.price:.2f} {currency}`'
        f'   {prev_label}: `{stock.prev_close:.2f}`'
    )
    change_line = f'   漲跌: `{sign}{stock.change:.2f}` \\({pct_esc}%\\)'
    return price_line, change_line


def _format_rich_block(stock: RichStockData) -> str:
    """Build a single stock's MarkdownV2 block with technical indicators.

    Args:
        stock: RichStockData containing price and indicator fields.

    Returns:
        Multi-line MarkdownV2 string for one stock.
    """
    arrow = '🔺' if stock.change >= 0 else '🔻'
    currency = 'TWD' if stock.market == 'TW' else 'USD'
    price_line, change_line = _build_price_change_lines(stock, currency)

    lines = [
        f'{arrow} *{_escape_md(stock.symbol)}* {_escape_md(stock.display_name)}',
        price_line,
        change_line,
    ]

    if stock.avg_cost is not None and stock.shares is not None:
        pnl_pct = (
            (stock.price - stock.avg_cost) / stock.avg_cost * 100
            if stock.avg_cost
            else 0.0
        )
        pnl_sign = '+' if pnl_pct >= 0 else ''
        pnl_pct_esc = _escape_md(f'{pnl_sign}{pnl_pct:.2f}')
        cost_esc = _escape_md(f'{stock.avg_cost:.2f}')
        lines.append('   ─── 持倉 ───')
        lines.append(
            f'   持股: `{stock.shares:,}`   成本: `{cost_esc}` \\({pnl_pct_esc}%\\)'
        )
        if stock.unrealized_pnl is not None:
            pnl_abs_sign = '+' if stock.unrealized_pnl >= 0 else ''
            pnl_abs_esc = _escape_md(f'{pnl_abs_sign}{stock.unrealized_pnl:,.0f}')
            lines.append(f'   損益: `{pnl_abs_esc} {currency}`')

    if stock.rsi is not None:
        rsi_tag = (
            '  ⚠️超買' if stock.rsi >= 70 else ('  ⚠️超賣' if stock.rsi <= 30 else '')
        )
        lines.append(f'   RSI\\(14\\): `{stock.rsi:.1f}`{rsi_tag}')

    ma_parts = []
    if stock.ma20 is not None:
        d = '↑' if stock.price > stock.ma20 else '↓'
        ma_parts.append(f'MA20:{stock.ma20:.0f}{d}')
    if stock.ma50 is not None:
        d = '↑' if stock.price > stock.ma50 else '↓'
        ma_parts.append(f'MA50:{stock.ma50:.0f}{d}')
    if ma_parts:
        lines.append(f'   均線: `{"  ".join(ma_parts)}`')

    if stock.week52_high is not None and stock.week52_low is not None:
        h, l_v = stock.week52_high, stock.week52_low
        if h != l_v:
            pos = (stock.price - l_v) / (h - l_v) * 100
            pos_esc = _escape_md(f'{pos:.0f}')
            lines.append(
                f'   近期區間: `{l_v:.2f} ─── {stock.price:.2f}'
                f' ─── {h:.2f}` \\({pos_esc}%位置\\)'
            )

    ind = IndicatorResult(
        rsi=stock.rsi,
        macd=stock.macd,
        macd_signal=stock.macd_signal,
        macd_hist=stock.macd_hist,
        ma20=stock.ma20,
        ma50=stock.ma50,
        bb_upper=stock.bb_upper,
        bb_mid=stock.bb_mid,
        bb_lower=stock.bb_lower,
        volume_today=stock.volume,
        volume_avg20=stock.volume_avg20,
        week52_high=stock.week52_high,
        week52_low=stock.week52_low,
    )
    result = score_stock(stock.price, stock.change_pct, ind)
    if '看漲' in result.verdict:
        emoji = '📈'
    elif '看跌' in result.verdict:
        emoji = '📉'
    else:
        emoji = '⚖️'
    lines.append('   ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄')
    score_esc = _escape_md(str(result.score))
    lines.append(f'   {emoji} *{_escape_md(result.verdict)}* \\(評分 {score_esc}/8\\)')
    for reason in result.bull_reasons:
        lines.append(f'   ✅ {_escape_md(reason)}')
    for reason in result.bear_reasons:
        lines.append(f'   ❌ {_escape_md(reason)}')

    signal = _calc_cost_signal(
        stock.price,
        stock.week52_high,
        stock.ma50,
        stock.market,
        symbol=stock.symbol,
    )
    if signal:
        lines.append(signal)

    return '\n'.join(lines)


def format_rich_stock_message(
    stocks: list[RichStockData],
    market: Literal['TW', 'US'],
    now: datetime,
) -> str:
    """Build a MarkdownV2 Telegram message with technical indicators for all stocks.

    Args:
        stocks: Non-empty list of RichStockData instances.
        market: 'TW' for Taiwan stocks, 'US' for US equities.
        now: Timestamp for the message header (Asia/Taipei time).

    Returns:
        Complete MarkdownV2 message string ready to send.
    """
    header = '📈 *台股定時推播*' if market == 'TW' else '📊 *美股定時推播*'
    date_str = _escape_md(now.strftime('%Y-%m-%d %H:%M'))
    sep = '\\-' * 25

    lines = [header, f'🕐 {date_str} \\| Asia/Taipei', sep, '']
    for stock in stocks:
        lines.append(_format_rich_block(stock))
        lines.append('')
    lines += [sep, '_由 FastAPI Stock Bot 自動產生_']
    return '\n'.join(lines)


def reply_to_chat(chat_id: str, text: str) -> bool:
    """Send a plain-text reply to a Telegram chat.

    Used by the webhook router to respond to user commands.
    Falls back silently on error so the caller can still return HTTP 200.

    Args:
        chat_id: Telegram chat ID to reply to.
        text: Plain-text message content (no parse_mode).

    Returns:
        True if the message was delivered successfully, False otherwise.
    """
    if not TELEGRAM_TOKEN:
        logger.error('TELEGRAM_TOKEN is not configured')
        return False

    url = f'{_TELEGRAM_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text}

    try:
        response = httpx.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info('Reply sent to chat_id=%s', chat_id)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            'Telegram API error for chat_id=%s: %s %s',
            chat_id,
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except httpx.RequestError as exc:
        logger.error('Telegram request failed for chat_id=%s: %s', chat_id, exc)
        return False


def send_rich_stock_message(
    user_id: str,
    stocks: list[RichStockData],
    market: Literal['TW', 'US'],
) -> bool:
    """Send a MarkdownV2 rich stock report to a Telegram user.

    Args:
        user_id: Telegram chat/user ID.
        stocks: List of RichStockData to include; must be non-empty.
        market: 'TW' or 'US', determines message header and currency label.

    Returns:
        True if the message was delivered successfully, False otherwise.
    """
    if not TELEGRAM_TOKEN:
        logger.error('TELEGRAM_TOKEN is not configured')
        return False

    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo('Asia/Taipei'))
    text = format_rich_stock_message(stocks, market, now)
    url = f'{_TELEGRAM_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': user_id, 'text': text, 'parse_mode': 'MarkdownV2'}

    try:
        response = httpx.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info(
            'Rich Telegram message sent to user_id=%s market=%s', user_id, market
        )
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            'Telegram API error for user_id=%s: %s %s',
            user_id,
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except httpx.RequestError as exc:
        logger.error('Telegram request failed for user_id=%s: %s', user_id, exc)
        return False
