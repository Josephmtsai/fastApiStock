"""Tests for the news_repo module (yfinance news fetch + Redis cache)."""

from unittest.mock import MagicMock, patch

import pytest

from fastapistock.repositories.news_repo import NewsItem, fetch_news


def _make_cache_miss() -> MagicMock:
    m = MagicMock()
    m.get.return_value = None
    return m


def test_fetch_news_cache_hit_skips_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    cached = {'items': [{'title': 'Good news', 'url': 'http://x.com'}]}
    fake_cache = MagicMock()
    fake_cache.get.return_value = cached
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with patch('yfinance.Ticker') as mock_ticker:
        result = fetch_news('AAPL', 'US')

    mock_ticker.assert_not_called()
    assert result == [NewsItem(title='Good news', url='http://x.com')]


def test_fetch_news_cache_miss_calls_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    mock_ticker = MagicMock()
    mock_ticker.news = [
        {
            'id': 'abc',
            'content': {'title': 'Breaking', 'canonicalUrl': {'url': 'http://y.com'}},
        }
    ]

    with patch('yfinance.Ticker', return_value=mock_ticker):
        with patch('time.sleep'):
            result = fetch_news('AAPL', 'US')

    assert result == [NewsItem(title='Breaking', url='http://y.com')]
    fake_cache.put.assert_called_once()


def test_fetch_news_yfinance_exception_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with patch('yfinance.Ticker', side_effect=Exception('network error')):
        with patch('time.sleep'):
            result = fetch_news('2330', 'TW')

    assert result == []


def test_fetch_news_empty_cache_falls_through_to_yfinance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit with items=[] must fall through to yfinance (stale-cache bypass)."""
    fake_cache = MagicMock()
    fake_cache.get.return_value = {'items': []}  # stale empty entry
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    mock_ticker = MagicMock()
    mock_ticker.news = [
        {
            'id': 'xyz',
            'content': {
                'title': 'Fresh headline',
                'canonicalUrl': {'url': 'http://fresh.com'},
            },
        }
    ]

    with patch('yfinance.Ticker', return_value=mock_ticker):
        with patch('time.sleep'):
            result = fetch_news('2330', 'TW')

    assert result == [NewsItem(title='Fresh headline', url='http://fresh.com')]
    fake_cache.put.assert_called_once()


def test_fetch_news_tw_uses_tw_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    captured: dict[str, str] = {}

    def fake_ticker(sym: str) -> MagicMock:
        captured['sym'] = sym
        m = MagicMock()
        m.news = [
            {
                'id': 'x',
                'content': {'title': 'Test', 'canonicalUrl': {'url': 'http://z.com'}},
            }
        ]
        return m

    with patch('yfinance.Ticker', side_effect=fake_ticker):
        with patch('time.sleep'):
            fetch_news('2330', 'TW')

    assert captured['sym'] == '2330.TW'


def test_fetch_news_cache_key_is_date_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache key must include today's date so stale prior-day entries are bypassed."""
    from datetime import date

    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    mock_ticker = MagicMock()
    mock_ticker.news = []

    with patch('yfinance.Ticker', return_value=mock_ticker):
        with patch('time.sleep'):
            fetch_news('AAPL', 'US')

    today = date.today().isoformat()
    expected_key = f'news:US:AAPL:{today}'
    assert fake_cache.get.call_args[0][0] == expected_key
