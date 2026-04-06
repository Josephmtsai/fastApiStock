"""Router for Taiwan stock data endpoints.

All routes live under /api/v1/stock.  Rate limiting is applied globally
by the middleware layer in main.py, not per-route.
"""

import logging

from fastapi import APIRouter

from fastapistock.schemas.common import ResponseEnvelope
from fastapistock.schemas.stock import StockData
from fastapistock.services.stock_service import get_stocks

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/stock', tags=['stocks'])


@router.get(
    '/{id}',
    response_model=ResponseEnvelope[list[StockData]],
    summary='Get quotes for one or more Taiwan stocks',
)
async def get_stock_quotes(id: str) -> ResponseEnvelope[list[StockData]]:
    """Return price snapshots for comma-separated Taiwan stock codes.

    Args:
        id: One or more Taiwan stock codes joined by commas,
            e.g. '0050,2330,2317'.

    Returns:
        ResponseEnvelope containing a list of StockData on success.
    """
    codes = [c.strip() for c in id.split(',') if c.strip()]
    logger.info('Stock quote request for codes=%s', codes)
    stocks = get_stocks(codes)
    return ResponseEnvelope(status='success', data=stocks)
