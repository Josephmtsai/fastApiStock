"""Repository for fetching stock news from Google News RSS (zh-TW)."""

from __future__ import annotations

import logging
import random
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Literal

import httpx

from fastapistock.cache import redis_cache as _cache

logger = logging.getLogger(__name__)

_CACHE_TTL = 4 * 60 * 60  # 4 hours
_MAX_FETCH = 5  # fetch up to 5; service trims to max_items
_RSS_URL = 'https://news.google.com/rss/search'
_RSS_PARAMS = {'hl': 'zh-TW', 'gl': 'TW', 'ceid': 'TW:zh-Hant'}


@dataclass(frozen=True)
class NewsItem:
    """Single news headline for a stock."""

    title: str
    url: str
    published: str = ''  # raw RFC-822 pubDate string, not parsed
    source: str = ''  # media outlet name (<source> element text)


def _build_query(symbol: str, market: Literal['TW', 'US']) -> str:
    """Build the Google News search query for a stock symbol.

    TW symbols resolve to the Chinese company name via the local twstock
    mapping (zero network calls); US symbols use '{symbol} 股票'.

    Args:
        symbol: Stock symbol (e.g. '2330' for TW, 'AAPL' for US).
        market: 'TW' or 'US'.

    Returns:
        Search query string, e.g. '台積電' or 'AAPL 股票'.
    """
    if market == 'TW':
        import twstock  # type: ignore[import-untyped]

        info = twstock.codes.get(symbol)
        if info is not None and info.name:
            return str(info.name)
    return f'{symbol} 股票'


def _clean_title(title: str, source: str) -> str:
    """Strip the trailing ' - {source}' suffix Google News appends to titles.

    Args:
        title: Raw RSS item title.
        source: Media outlet name from the <source> element.

    Returns:
        Cleaned title; original title when source is empty or does not match.
    """
    suffix = f' - {source}'
    trimmed = title.rstrip()
    if source and trimmed.endswith(suffix):
        return trimmed[: -len(suffix)].strip()
    return title.strip()


def _parse_rss(xml_text: str) -> list[NewsItem]:
    """Parse a Google News RSS document into NewsItem objects.

    Args:
        xml_text: Raw RSS XML string.

    Returns:
        Up to _MAX_FETCH NewsItem objects; items with empty cleaned titles
        are discarded.
    """
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for item in root.iter('item'):
        if len(items) >= _MAX_FETCH:
            break
        title = item.findtext('title') or ''
        source = (item.findtext('source') or '').strip()
        cleaned = _clean_title(title, source)
        if not cleaned:
            continue
        items.append(
            NewsItem(
                title=cleaned,
                url=(item.findtext('link') or '').strip(),
                published=(item.findtext('pubDate') or '').strip(),
                source=source,
            )
        )
    return items


def fetch_news(symbol: str, market: Literal['TW', 'US']) -> list[NewsItem]:
    """Fetch recent news for a stock from Google News RSS (Redis-cached, 4 h TTL).

    Args:
        symbol: Stock symbol (e.g. '2330' for TW, 'AAPL' for US).
        market: 'TW' uses the Chinese company name as query; 'US' uses
            '{symbol} 股票'.

    Returns:
        List of NewsItem; empty list on any failure.
    """
    today = date.today().isoformat()
    cache_key = f'news:v2:{market}:{symbol}:{today}'
    cached = _cache.get(cache_key)
    if cached is not None:
        raw_items: list[dict[str, str]] = cached.get('items', [])  # type: ignore[assignment]
        if raw_items:
            return [
                NewsItem(
                    title=i['title'],
                    url=i['url'],
                    published=i.get('published', ''),
                    source=i.get('source', ''),
                )
                for i in raw_items
            ]

    time.sleep(random.uniform(0.5, 1.5))

    try:
        response = httpx.get(
            _RSS_URL,
            params={'q': _build_query(symbol, market), **_RSS_PARAMS},
            timeout=10,
            follow_redirects=True,
        )
        response.raise_for_status()
        items = _parse_rss(response.text)
    except (httpx.HTTPError, ET.ParseError) as exc:
        logger.warning('News fetch failed for %s: %s', symbol, exc)
        return []

    _cache.put(
        cache_key,
        {
            'items': [
                {
                    'title': i.title,
                    'url': i.url,
                    'published': i.published,
                    'source': i.source,
                }
                for i in items
            ]
        },
        _CACHE_TTL,
    )
    return items
