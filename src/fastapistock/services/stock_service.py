"""Business logic for the stock domain.

Orchestrates cache-first lookup → repository fetch → cache write.
No HTTP imports belong here; all external I/O goes through repositories.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import cast

from fastapistock.cache import redis_cache
from fastapistock.config import (
    PORTFOLIO_CACHE_TTL,
    TW_RICH_CACHE_TTL,
    TW_STOCK_CACHE_TTL,
)
from fastapistock.repositories.portfolio_repo import PortfolioEntry, fetch_portfolio
from fastapistock.repositories.twstock_repo import fetch_stock, fetch_tw_rich_stock
from fastapistock.schemas.stock import RichStockData, StockData

logger = logging.getLogger(__name__)

_MAX_WORKERS = 5  # parallel yfinance fetches for multi-stock requests
_PORTFOLIO_CACHE_KEY = 'portfolio:tw'


def _cache_key(code: str) -> str:
    """Build the Redis cache key for today's quote of *code*.

    Args:
        code: Taiwan stock code (e.g. '0050').

    Returns:
        Cache key string (e.g. ``'stock:0050:2026-04-04'``).
    """
    return f'stock:{code}:{date.today().isoformat()}'


def _rich_cache_key(code: str) -> str:
    """Build the Redis cache key for today's rich snapshot of *code*.

    Args:
        code: Taiwan stock code (e.g. '0050').

    Returns:
        Cache key string (e.g. ``'rich_tw:0050:2026-04-04'``).
    """
    return f'rich_tw:{code}:{date.today().isoformat()}'


def get_stock(code: str) -> StockData:
    """Return the latest snapshot for a single Taiwan stock code.

    Checks the Redis cache first; falls back to the yfinance repository
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
    logger.info('Cache lookup: key=%s', key)
    cached = redis_cache.get(key)
    if cached is not None:
        logger.info('Cache hit for %s', code)
        return StockData.model_validate(cached)

    logger.info('Cache miss for %s — fetching from yfinance', code)
    stock = fetch_stock(code)
    logger.info(
        'Fetch complete for %s — storing in cache (ttl=%ds)', code, TW_STOCK_CACHE_TTL
    )
    redis_cache.put(key, stock.model_dump(), TW_STOCK_CACHE_TTL)
    return stock


def get_stocks(codes: list[str]) -> list[StockData]:
    """Return snapshots for a list of Taiwan stock codes in parallel.

    Cache-hit codes are resolved immediately; only cache-miss codes are
    forwarded to the thread pool for concurrent yfinance fetches.

    Args:
        codes: Non-empty list of Taiwan stock codes.

    Returns:
        List of StockData in the same order as *codes*.

    Raises:
        StockNotFoundError: If any symbol in *codes* is not found.
    """
    cleaned = [c.strip() for c in codes]

    # Resolve cache hits synchronously to avoid thread-pool overhead.
    results: dict[str, StockData] = {}
    miss_codes: list[str] = []
    for code in cleaned:
        key = _cache_key(code)
        cached = redis_cache.get(key)
        if cached is not None:
            logger.info('Cache hit for %s', code)
            results[code] = StockData.model_validate(cached)
        else:
            miss_codes.append(code)

    # Fetch all cache misses in parallel.
    if miss_codes:
        logger.info(
            'Parallel fetch for %d cache-miss stocks: %s', len(miss_codes), miss_codes
        )
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(miss_codes))) as pool:
            future_to_code = {pool.submit(get_stock, code): code for code in miss_codes}
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                results[code] = future.result()  # re-raises StockNotFoundError if any

    return [results[code] for code in cleaned]


def get_rich_tw_stock(code: str) -> RichStockData:
    """Return the rich technical-analysis snapshot for one TW stock (cache-first).

    Args:
        code: Taiwan stock code (e.g. '2330').

    Returns:
        A populated RichStockData instance.

    Raises:
        StockNotFoundError: Propagated from the repository when the symbol
            yields no data from Yahoo Finance.
    """
    key = _rich_cache_key(code)
    cached = redis_cache.get(key)
    if cached is not None:
        logger.info('Rich cache hit for %s', code)
        return RichStockData.model_validate(cached)

    logger.info('Rich cache miss for %s — fetching', code)
    stock = fetch_tw_rich_stock(code)
    redis_cache.put(key, stock.model_dump(), TW_RICH_CACHE_TTL)
    return stock


def _get_cached_portfolio() -> dict[str, PortfolioEntry]:
    """Return portfolio from Redis cache, fetching live on miss or unavailability.

    On a cache hit, deserialises each entry from the stored dict.
    On a cache miss or Redis unavailability (get returns None), fetches live
    from Google Sheets and stores the result (TTL=PORTFOLIO_CACHE_TTL) when
    the portfolio is non-empty.

    Returns:
        Mapping from symbol to PortfolioEntry; empty dict when portfolio is
        unconfigured or the Sheets request fails.
    """
    raw = redis_cache.get(_PORTFOLIO_CACHE_KEY)
    if raw is not None:
        logger.info('Portfolio cache hit')
        portfolio: dict[str, PortfolioEntry] = {}
        for symbol, entry_raw in raw.items():
            entry_dict = cast(dict[str, object], entry_raw)
            portfolio[symbol] = PortfolioEntry(
                symbol=cast(str, entry_dict['symbol']),
                shares=int(cast(float, entry_dict['shares'])),
                avg_cost=float(cast(float, entry_dict['avg_cost'])),
                unrealized_pnl=float(cast(float, entry_dict['unrealized_pnl'])),
            )
        return portfolio

    logger.info('Portfolio cache miss — fetching from Google Sheets')
    live = fetch_portfolio()
    if live:
        serialised: dict[str, object] = {
            sym: {
                'symbol': e.symbol,
                'shares': e.shares,
                'avg_cost': e.avg_cost,
                'unrealized_pnl': e.unrealized_pnl,
            }
            for sym, e in live.items()
        }
        redis_cache.put(_PORTFOLIO_CACHE_KEY, serialised, PORTFOLIO_CACHE_TTL)
    return live


def _merge_portfolio(
    stocks: list[RichStockData],
    portfolio: dict[str, PortfolioEntry],
) -> list[RichStockData]:
    """Merge portfolio positions into a list of RichStockData (pure function).

    For each stock whose symbol appears in *portfolio*, a new RichStockData
    is created via ``model_copy`` with ``avg_cost``, ``unrealized_pnl``, and
    ``shares`` populated.  Stocks absent from *portfolio* are returned unchanged.

    Args:
        stocks: List of RichStockData snapshots to enrich.
        portfolio: Mapping from symbol to PortfolioEntry.

    Returns:
        New list of RichStockData with portfolio fields merged where available.
    """
    merged: list[RichStockData] = []
    for stock in stocks:
        entry = portfolio.get(stock.symbol)
        if entry is not None:
            merged.append(
                stock.model_copy(
                    update={
                        'avg_cost': entry.avg_cost,
                        'unrealized_pnl': entry.unrealized_pnl,
                        'shares': entry.shares,
                    }
                )
            )
        else:
            merged.append(stock)
    return merged


def get_rich_tw_stocks(codes: list[str]) -> list[RichStockData]:
    """Return rich snapshots for multiple TW stocks using parallel fetching.

    Cache hits are resolved immediately; misses are fetched concurrently.

    Args:
        codes: Non-empty list of Taiwan stock codes.

    Returns:
        List of RichStockData in the same order as *codes*.

    Raises:
        StockNotFoundError: If any symbol in *codes* is not found.
    """
    cleaned = [c.strip() for c in codes]
    results: dict[str, RichStockData] = {}
    miss_codes: list[str] = []

    for code in cleaned:
        cached = redis_cache.get(_rich_cache_key(code))
        if cached is not None:
            results[code] = RichStockData.model_validate(cached)
        else:
            miss_codes.append(code)

    if miss_codes:
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(miss_codes))) as pool:
            future_to_code = {pool.submit(get_rich_tw_stock, c): c for c in miss_codes}
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                results[code] = future.result()

    stocks = [results[code] for code in cleaned]
    portfolio = _get_cached_portfolio()
    return _merge_portfolio(stocks, portfolio)
