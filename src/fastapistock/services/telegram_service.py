"""Telegram notification service.

Sends formatted stock information to a Telegram user via the Bot API.
"""

import logging

import httpx

from fastapistock.config import TELEGRAM_TOKEN
from fastapistock.schemas.stock import StockData

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = 'https://api.telegram.org'
_REQUEST_TIMEOUT = 10


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
