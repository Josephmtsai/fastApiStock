"""Tests for the news_service module (keyword-based sentiment classification)."""

from unittest.mock import patch

import pytest

from fastapistock.repositories.news_repo import NewsItem
from fastapistock.services.news_service import (
    SentimentNews,
    classify_sentiment,
    get_sentiment_news,
)


@pytest.mark.parametrize(
    'title,expected',
    [
        ('AI晶片需求強勁，台積電Q2展望樂觀', '正面'),
        ('外資連續買超3日', '正面'),
        ('Apple beat expectations', '正面'),
        ('Stock surged 5%', '正面'),
        ('iPhone銷量下滑，分析師下修評等', '負面'),
        ('Company reported a loss', '負面'),
        ('Analyst downgrade issued', '負面'),
        ('Apple reports quarterly results', '中性'),
        ('市場今日交易平穩', '中性'),
    ],
)
def test_classify_sentiment(title: str, expected: str) -> None:
    assert classify_sentiment(title) == expected


def test_get_sentiment_news_returns_max_items() -> None:
    items = [
        NewsItem(title='Stock surged', url='http://a.com'),
        NewsItem(title='Earnings miss', url='http://b.com'),
        NewsItem(title='Normal news', url='http://c.com'),
    ]
    with patch('fastapistock.services.news_service.fetch_news', return_value=items):
        result = get_sentiment_news('AAPL', 'US', max_items=2)
    assert len(result) == 2
    assert result[0] == SentimentNews(title='Stock surged', sentiment='正面')
    assert result[1] == SentimentNews(title='Earnings miss', sentiment='負面')


def test_get_sentiment_news_empty_returns_empty() -> None:
    with patch('fastapistock.services.news_service.fetch_news', return_value=[]):
        result = get_sentiment_news('2330', 'TW')
    assert result == []
