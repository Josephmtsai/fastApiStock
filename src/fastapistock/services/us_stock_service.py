"""Business logic for US stock data.

Orchestrates cache-first lookup → repository fetch → cache write for
US equities. Mirrors stock_service.py but uses the us_stock_repo and
a distinct Redis key prefix ('us_stock:').
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import cast

from fastapistock.cache import redis_cache
from fastapistock.config import PORTFOLIO_CACHE_TTL
from fastapistock.repositories.portfolio_repo import PortfolioEntry, fetch_portfolio_us
from fastapistock.repositories.us_stock_repo import fetch_us_stock
from fastapistock.schemas.stock import RichStockData

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes
_MAX_WORKERS = 5
_US_PORTFOLIO_CACHE_KEY = 'portfolio:us'


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

    stocks = [results[s] for s in cleaned]
    portfolio = _get_cached_us_portfolio()
    return _merge_us_portfolio(stocks, portfolio)


def _get_cached_us_portfolio() -> dict[str, PortfolioEntry]:
    """Return US portfolio from Redis cache, fetching live on miss.

    Returns:
        Mapping from normalized symbol to PortfolioEntry.
    """
    raw = redis_cache.get(_US_PORTFOLIO_CACHE_KEY)
    if raw is not None and isinstance(raw, dict):
        logger.info('US portfolio cache hit')
        portfolio: dict[str, PortfolioEntry] = {}
        try:
            for symbol, entry_raw in raw.items():
                entry_dict = cast(dict[str, object], entry_raw)
                portfolio[symbol] = PortfolioEntry(
                    symbol=cast(str, entry_dict['symbol']),
                    shares=int(cast(float, entry_dict['shares'])),
                    avg_cost=float(cast(float, entry_dict['avg_cost'])),
                    unrealized_pnl=float(cast(float, entry_dict['unrealized_pnl'])),
                )
        except (KeyError, TypeError, ValueError):
            logger.warning('US portfolio cache payload malformed; refetching live')
            portfolio = {}
        else:
            return portfolio

    logger.info('US portfolio cache miss — fetching from Google Sheets')
    live = fetch_portfolio_us()
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
        redis_cache.put(_US_PORTFOLIO_CACHE_KEY, serialised, PORTFOLIO_CACHE_TTL)
    return live


def _merge_us_portfolio(
    stocks: list[RichStockData],
    portfolio: dict[str, PortfolioEntry],
) -> list[RichStockData]:
    """Merge US portfolio fields into rich stock snapshots.

    Args:
        stocks: US stock snapshots.
        portfolio: US portfolio mapping by normalized symbol.

    Returns:
        Stocks with avg_cost/unrealized_pnl/shares when matched.
    """
    merged: list[RichStockData] = []
    for stock in stocks:
        entry = portfolio.get(stock.symbol)
        if entry is None:
            merged.append(stock)
            continue
        merged.append(
            stock.model_copy(
                update={
                    'avg_cost': entry.avg_cost,
                    'unrealized_pnl': entry.unrealized_pnl,
                    'shares': entry.shares,
                }
            )
        )
    return merged
