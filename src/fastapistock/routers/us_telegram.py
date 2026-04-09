"""Router for US stock Telegram notification endpoints.

All routes live under /api/v1/usMessage.  Rate limiting is applied
globally by the middleware layer in main.py, not per-route.
"""

import logging

from fastapi import APIRouter, Query

from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.schemas.common import ResponseEnvelope
from fastapistock.services.telegram_service import send_rich_stock_message
from fastapistock.services.us_stock_service import get_us_stocks

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/usMessage', tags=['us-telegram'])


@router.get(
    '/{id}',
    response_model=ResponseEnvelope[None],
    summary='Push US stock info to a Telegram user',
)
async def send_us_telegram_stock_info(
    id: str,
    stock: str = Query(default='', description='Comma-separated US stock tickers'),
) -> ResponseEnvelope[None]:
    """Fetch US stock data and push a formatted MarkdownV2 message to a Telegram user.

    Non-alpha tickers in *stock* are silently ignored. Tickers are uppercased
    automatically before fetching.

    Args:
        id: Telegram user/chat ID to push the message to.
        stock: Comma-separated US stock tickers (e.g. 'AAPL,TSLA').
            Non-alphabetic tokens are ignored.

    Returns:
        ResponseEnvelope with status 'success' when the message is sent,
        or 'error' with a descriptive message otherwise.
    """
    symbols = [
        s.strip().upper() for s in stock.split(',') if s.strip() and s.strip().isalpha()
    ]
    if not symbols:
        logger.info('No valid US tickers provided; skipping push')
        return ResponseEnvelope(
            status='error', message='No valid stock tickers provided'
        )

    try:
        stocks = get_us_stocks(symbols)
    except StockNotFoundError as exc:
        logger.warning('US stock not found during Telegram push: %s', exc)
        return ResponseEnvelope(status='error', message=str(exc))

    if not stocks:
        return ResponseEnvelope(status='error', message='No stock data retrieved')

    sent = send_rich_stock_message(id, stocks, market='US')
    if sent:
        return ResponseEnvelope(status='success', message=f'Message sent to {id}')
    return ResponseEnvelope(status='error', message='Failed to send Telegram message')
