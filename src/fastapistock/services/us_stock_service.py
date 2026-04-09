"""Business logic for US stock data.

Orchestrates cache-first lookup → repository fetch → cache write for
US equities. Mirrors stock_service.py but uses the us_stock_repo and
a distinct Redis key prefix ('us_stock:').
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from fastapistock.cache import redis_cache
from fastapistock.repositories.us_stock_repo import fetch_us_stock
from fastapistock.schemas.stock import RichStockData

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes
_MAX_WORKERS = 5


def _cache_key(symbol: str) -> str:
    """Build the Redis cache key for today's US stock snapshot.

    Args:
        symbol: US stock ticker in uppercase (e.g. 'AAPL').

    Returns:
        Cache key string (e.g. ``'us_stock:AAPL:2026-04-04'``).
    """
    return f'us_stock:{symbol}:{date.today().isoformat()}'


def get_us_stock(symbol: str) -> RichStockData:
    """Return the rich snapshot for one US stock symbol (cache-first).

    Args:
        symbol: US stock ticker in uppercase (e.g. 'TSLA').

    Returns:
        A populated RichStockData instance with market='US'.

    Raises:
        StockNotFoundError: Propagated from the repository when the symbol
            yields no data from Yahoo Finance.
    """
    key = _cache_key(symbol)
    cached = redis_cache.get(key)
    if cached is not None:
        logger.info('US cache hit for %s', symbol)
        return RichStockData.model_validate(cached)

    logger.info('US cache miss for %s — fetching', symbol)
    stock = fetch_us_stock(symbol)
    redis_cache.put(key, stock.model_dump(), _CACHE_TTL)
    return stock


def get_us_stocks(symbols: list[str]) -> list[RichStockData]:
    """Return rich snapshots for multiple US stocks using parallel fetching.

    Cache hits are resolved immediately; misses are fetched concurrently.

    Args:
        symbols: Non-empty list of US stock tickers in uppercase.

    Returns:
        List of RichStockData in the same order as *symbols*.

    Raises:
        StockNotFoundError: If any symbol in *symbols* is not found.
    """
    cleaned = [s.strip().upper() for s in symbols]
    results: dict[str, RichStockData] = {}
    miss_symbols: list[str] = []

    for symbol in cleaned:
        cached = redis_cache.get(_cache_key(symbol))
        if cached is not None:
            results[symbol] = RichStockData.model_validate(cached)
        else:
            miss_symbols.append(symbol)

    if miss_symbols:
        with ThreadPoolExecutor(
            max_workers=min(_MAX_WORKERS, len(miss_symbols))
        ) as pool:
            future_to_sym = {pool.submit(get_us_stock, s): s for s in miss_symbols}
            for future in as_completed(future_to_sym):
                symbol = future_to_sym[future]
                results[symbol] = future.result()

    return [results[s] for s in cleaned]
