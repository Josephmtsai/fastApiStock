"""Repository for fetching stock news from Yahoo Finance."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date
from typing import Literal

import yfinance as yf

from fastapistock.cache import redis_cache as _cache

logger = logging.getLogger(__name__)

_CACHE_TTL = 4 * 60 * 60  # 4 hours
_MAX_FETCH = 5  # fetch up to 5; service trims to max_items


@dataclass(frozen=True)
class NewsItem:
    """Single news headline for a stock."""

    title: str
    url: str


def fetch_news(symbol: str, market: Literal['TW', 'US']) -> list[NewsItem]:
    """Fetch recent news for a stock from Yahoo Finance (Redis-cached, 4 h TTL).

    Args:
        symbol: Stock symbol (e.g. '2330' for TW, 'AAPL' for US).
        market: 'TW' appends '.TW' suffix for yfinance; 'US' uses symbol as-is.

    Returns:
        List of NewsItem; empty list on any failure.
    """
    today = date.today().isoformat()
    cache_key = f'news:{market}:{symbol}:{today}'
    cached = _cache.get(cache_key)
    if cached is not None:
        raw_items: list[dict[str, str]] = cached.get('items', [])  # type: ignore[assignment]
        if raw_items:
            return [NewsItem(title=i['title'], url=i['url']) for i in raw_items]

    time.sleep(random.uniform(0.5, 1.5))

    ticker_sym = f'{symbol}.TW' if market == 'TW' else symbol
    try:
        raw_news: list[dict[str, object]] = yf.Ticker(ticker_sym).news or []
    except Exception as exc:
        logger.warning('News fetch failed for %s: %s', symbol, exc)
        return []

    items = []
    for n in raw_news[:_MAX_FETCH]:
        content: dict[str, object] = n.get('content') or {}  # type: ignore[assignment]
        title = str(content.get('title') or n.get('title') or '')
        canonical: dict[str, object] = content.get('canonicalUrl') or {}  # type: ignore[assignment]
        url = str(canonical.get('url') or n.get('link') or '')
        if title:
            items.append(NewsItem(title=title, url=url))

    _cache.put(
        cache_key,
        {'items': [{'title': i.title, 'url': i.url} for i in items]},
        _CACHE_TTL,
    )
    return items
