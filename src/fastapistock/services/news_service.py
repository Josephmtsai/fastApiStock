"""Keyword-based sentiment classification for stock news headlines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapistock.repositories.news_repo import NewsItem, fetch_news

Sentiment = Literal['正面', '中性', '負面']

_POSITIVE: frozenset[str] = frozenset(
    [
        '強勁',
        '樂觀',
        '買超',
        '創高',
        '成長',
        '上漲',
        '突破',
        '獲利',
        '亮眼',
        'beat',
        'surge',
        'rally',
        'gain',
        'rise',
        'strong',
        'upgrade',
    ]
)
_NEGATIVE: frozenset[str] = frozenset(
    [
        '下滑',
        '虧損',
        '賣超',
        '暴跌',
        '警告',
        '下跌',
        '跌破',
        '衰退',
        '下修',
        'miss',
        'drop',
        'decline',
        'downgrade',
        'fall',
        'loss',
        'weak',
        'cut',
    ]
)


@dataclass(frozen=True)
class SentimentNews:
    """News headline with classified sentiment."""

    title: str
    sentiment: Sentiment


def classify_sentiment(title: str) -> Sentiment:
    """Classify a headline as 正面, 負面, or 中性 using keyword matching.

    Args:
        title: News headline text (Chinese or English).

    Returns:
        Sentiment label; defaults to '中性' when no keyword matches.
    """
    lower = title.lower()
    if any(kw in lower for kw in _POSITIVE):
        return '正面'
    if any(kw in lower for kw in _NEGATIVE):
        return '負面'
    return '中性'


def get_sentiment_news(
    symbol: str,
    market: Literal['TW', 'US'],
    max_items: int = 2,
) -> list[SentimentNews]:
    """Return up to *max_items* classified news items for *symbol*.

    Args:
        symbol: Stock symbol.
        market: 'TW' or 'US'.
        max_items: Maximum number of items to return (default 2).

    Returns:
        List of SentimentNews; empty list when no news available.
    """
    news: list[NewsItem] = fetch_news(symbol, market)
    return [
        SentimentNews(title=item.title, sentiment=classify_sentiment(item.title))
        for item in news[:max_items]
    ]
