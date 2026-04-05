"""Router for Telegram notification endpoints.

All routes live under /api/v1/tgMessage and are rate-limited
in accordance with Constitution Principle III.
"""

import logging

from fastapi import APIRouter, Query, Request

from fastapistock.rate_limit import limiter
from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.schemas.common import ResponseEnvelope
from fastapistock.services.stock_service import get_stocks
from fastapistock.services.telegram_service import send_stock_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/tgMessage', tags=['telegram'])


@router.get(
    '/{id}',
    response_model=ResponseEnvelope[None],
    summary='Push stock info to a Telegram user',
)
@limiter.limit('30/minute')
async def send_telegram_stock_info(
    request: Request,
    id: str,
    stock: str = Query(default='', description='Comma-separated Taiwan stock codes'),
) -> ResponseEnvelope[None]:
    """Fetch stock data and push a formatted message to a Telegram user.

    Non-numeric stock codes in *stock* are silently ignored.
    If no valid codes remain or no data is found, the message is not sent.

    Args:
        request: FastAPI request object (required by slowapi rate limiter).
        id: Telegram user/chat ID to push the message to.
        stock: Comma-separated Taiwan stock codes (e.g. '0050,2330').
            Non-numeric tokens are ignored.

    Returns:
        ResponseEnvelope with status 'success' when the message is sent,
        or 'error' with a descriptive message otherwise.
    """
    codes = [c.strip() for c in stock.split(',') if c.strip() and c.strip().isdigit()]
    if not codes:
        logger.info('No valid numeric stock codes provided; skipping Telegram push')
        return ResponseEnvelope(status='error', message='No valid stock codes provided')

    try:
        stocks = get_stocks(codes)
    except StockNotFoundError as exc:
        logger.warning('Stock not found during Telegram push: %s', exc)
        return ResponseEnvelope(status='error', message=str(exc))

    if not stocks:
        return ResponseEnvelope(status='error', message='No stock data retrieved')

    sent = send_stock_message(id, stocks)
    if sent:
        return ResponseEnvelope(status='success', message=f'Message sent to {id}')
    return ResponseEnvelope(status='error', message='Failed to send Telegram message')
