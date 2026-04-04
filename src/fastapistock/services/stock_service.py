"""Business logic for the stock domain.

Orchestrates cache-first lookup → repository fetch → cache write.
No HTTP imports belong here; all external I/O goes through repositories.
"""

import logging
from datetime import date

from fastapistock.cache import file_cache
from fastapistock.repositories.twstock_repo import fetch_stock
from fastapistock.schemas.stock import StockData

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes


def _cache_key(code: str) -> str:
    """Build the file-cache key for today's quote of *code*.

    Args:
        code: Taiwan stock code (e.g. '0050').

    Returns:
        Cache key string (e.g. '0050/2026-04-03').
    """
    return f'{code}/{date.today().isoformat()}'


def get_stock(code: str) -> StockData:
    """Return the latest snapshot for a single Taiwan stock code.

    Checks the file cache first; falls back to the yfinance repository
    on a miss and stores the result before returning.

    Args:
        code: Taiwan stock code (e.g. '2330').

    Returns:
        A fully populated StockData instance.

    Raises:
        StockNotFoundError: Propagated from the repository when the
            symbol yields no data from Yahoo Finance.
    """
    key = _cache_key(code)
    cached = file_cache.get(key, _CACHE_TTL)
    if cached is not None:
        logger.debug('Cache hit for %s', code)
        return StockData.model_validate(cached)

    logger.info('Cache miss for %s – fetching from yfinance', code)
    stock = fetch_stock(code)
    file_cache.put(key, stock.model_dump())
    return stock


def get_stocks(codes: list[str]) -> list[StockData]:
    """Return snapshots for a list of Taiwan stock codes.

    Each code is resolved independently; errors for individual symbols
    are logged and re-raised so the caller decides how to handle them.

    Args:
        codes: Non-empty list of Taiwan stock codes.

    Returns:
        List of StockData in the same order as *codes*.

    Raises:
        StockNotFoundError: If any symbol in *codes* is not found.
    """
    results: list[StockData] = []
    for code in codes:
        stock = get_stock(code.strip())
        results.append(stock)
    return results
