"""Telegram notification service.

Sends formatted stock information to a Telegram user via the Bot API.
Provides both a simple plain-text sender (send_stock_message) and a rich
MarkdownV2 sender (send_rich_stock_message) with full technical indicators.
"""

import logging
import re
from datetime import datetime
from typing import Literal

import httpx

from fastapistock.config import TELEGRAM_TOKEN
from fastapistock.schemas.stock import RichStockData, StockData
from fastapistock.services.indicators import IndicatorResult, score_stock

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = 'https://api.telegram.org'
_REQUEST_TIMEOUT = 10

_MD_SPECIAL = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')


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
            f'現價: {s.price}\n'
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


def _format_rich_block(stock: RichStockData) -> str:
    """Build a single stock's MarkdownV2 block with technical indicators.

    Args:
        stock: RichStockData containing price and indicator fields.

    Returns:
        Multi-line MarkdownV2 string for one stock.
    """
    arrow = '🔺' if stock.change >= 0 else '🔻'
    sign = '+' if stock.change >= 0 else ''
    currency = 'TWD' if stock.market == 'TW' else 'USD'
    prev_label = '昨收' if stock.market == 'TW' else '前收'

    lines = [
        f'{arrow} *{_escape_md(stock.symbol)}* {_escape_md(stock.display_name)}',
        f'   現價: `{stock.price:.2f} {currency}`'
        f'   {prev_label}: `{stock.prev_close:.2f}`',
        f'   漲跌: `{sign}{stock.change:.2f}` \\({sign}{stock.change_pct:.2f}%\\)',
    ]

    if stock.rsi is not None:
        rsi_tag = (
            '  ⚠️超買' if stock.rsi >= 70 else ('  ⚠️超賣' if stock.rsi <= 30 else '')
        )
        lines.append(f'   RSI\\(14\\): `{stock.rsi:.1f}`{rsi_tag}')

    if (
        stock.macd is not None
        and stock.macd_signal is not None
        and stock.macd_hist is not None
    ):
        cross = '金叉↑' if stock.macd_hist > 0 else '死叉↓'
        lines.append(
            f'   MACD: `{stock.macd:.3f}` 訊: `{stock.macd_signal:.3f}`'
            f' 柱: `{stock.macd_hist:.3f}` \\({cross}\\)'
        )

    ma_parts = []
    if stock.ma20 is not None:
        d = '↑' if stock.price > stock.ma20 else '↓'
        ma_parts.append(f'MA20:{stock.ma20:.0f}{d}')
    if stock.ma50 is not None:
        d = '↑' if stock.price > stock.ma50 else '↓'
        ma_parts.append(f'MA50:{stock.ma50:.0f}{d}')
    if ma_parts:
        lines.append(f'   均線: `{"  ".join(ma_parts)}`')

    if (
        stock.bb_upper is not None
        and stock.bb_mid is not None
        and stock.bb_lower is not None
    ):
        bb_tag = ''
        if stock.price >= stock.bb_upper:
            bb_tag = '  ⚠️觸上軌'
        elif stock.price <= stock.bb_lower:
            bb_tag = '  ⚠️觸下軌'
        lines.append(
            f'   布林: `{stock.bb_lower:.2f} / {stock.bb_mid:.2f}'
            f' / {stock.bb_upper:.2f}`{bb_tag}'
        )

    if stock.volume_avg20 > 0:
        ratio = stock.volume / stock.volume_avg20
        vol_tag = '放量↑' if ratio > 1.5 else ('縮量↓' if ratio < 0.5 else '正常')
        lines.append(
            f'   成交量: `{stock.volume:,}` \\(均量比:{ratio:.1f}x {vol_tag}\\)'
        )

    if stock.week52_high is not None and stock.week52_low is not None:
        h, l_v = stock.week52_high, stock.week52_low
        if h != l_v:
            pos = (stock.price - l_v) / (h - l_v) * 100
            lines.append(
                f'   近期區間: `{l_v:.2f} ─── {stock.price:.2f}'
                f' ─── {h:.2f}` \\({pos:.0f}%位置\\)'
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
    lines.append(
        f'   {emoji} *{_escape_md(result.verdict)}* \\(評分 {result.score}/8\\)'
    )
    for reason in result.bull_reasons:
        lines.append(f'   ✅ {_escape_md(reason)}')
    for reason in result.bear_reasons:
        lines.append(f'   ❌ {_escape_md(reason)}')

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
