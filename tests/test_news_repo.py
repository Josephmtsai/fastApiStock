"""Tests for the news_repo module (Google News RSS fetch + Redis cache)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from fastapistock.repositories.news_repo import NewsItem, fetch_news

_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Google News</title>
<item>
  <title>台積電法說會釋利多 - 經濟日報</title>
  <link>https://news.google.com/rss/articles/abc</link>
  <pubDate>Fri, 04 Jul 2026 08:30:00 GMT</pubDate>
  <source url="https://money.udn.com">經濟日報</source>
</item>
<item>
  <title>台積電先進製程需求強勁</title>
  <link>https://news.google.com/rss/articles/def</link>
  <pubDate>Fri, 04 Jul 2026 09:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

_RSS_EMPTY_TITLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title> - 經濟日報</title>
  <link>https://news.google.com/rss/articles/ghi</link>
  <source url="https://money.udn.com">經濟日報</source>
</item>
</channel></rss>
"""

_RSS_NO_ITEMS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Google News</title></channel></rss>
"""


def _make_cache_miss() -> MagicMock:
    m = MagicMock()
    m.get.return_value = None
    return m


def _make_response(xml: str) -> MagicMock:
    resp = MagicMock()
    resp.text = xml
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_news_cache_hit_skips_http(monkeypatch: pytest.MonkeyPatch) -> None:
    cached = {
        'items': [
            {
                'title': '好消息',
                'url': 'http://x.com',
                'published': 'Fri, 04 Jul 2026 08:30:00 GMT',
                'source': '經濟日報',
            }
        ]
    }
    fake_cache = MagicMock()
    fake_cache.get.return_value = cached
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with patch('fastapistock.repositories.news_repo.httpx.get') as mock_get:
        result = fetch_news('AAPL', 'US')

    mock_get.assert_not_called()
    assert result == [
        NewsItem(
            title='好消息',
            url='http://x.com',
            published='Fri, 04 Jul 2026 08:30:00 GMT',
            source='經濟日報',
        )
    ]


def test_fetch_news_legacy_cache_payload_without_new_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache payloads lacking published/source default to empty strings."""
    fake_cache = MagicMock()
    fake_cache.get.return_value = {
        'items': [{'title': '好消息', 'url': 'http://x.com'}]
    }
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with patch('fastapistock.repositories.news_repo.httpx.get') as mock_get:
        result = fetch_news('AAPL', 'US')

    mock_get.assert_not_called()
    assert result == [NewsItem(title='好消息', url='http://x.com')]


def test_fetch_news_cache_miss_fetches_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_XML),
        ) as mock_get,
        patch('time.sleep') as mock_sleep,
    ):
        result = fetch_news('AAPL', 'US')

    mock_get.assert_called_once()
    mock_sleep.assert_called_once()
    assert result[0] == NewsItem(
        title='台積電法說會釋利多',
        url='https://news.google.com/rss/articles/abc',
        published='Fri, 04 Jul 2026 08:30:00 GMT',
        source='經濟日報',
    )
    fake_cache.put.assert_called_once()
    payload = fake_cache.put.call_args[0][1]
    assert payload['items'][0]['source'] == '經濟日報'


def test_fetch_news_title_suffix_kept_when_source_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item without <source> keeps its original title (E-7)."""
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_XML),
        ),
        patch('time.sleep'),
    ):
        result = fetch_news('AAPL', 'US')

    assert result[1].title == '台積電先進製程需求強勁'
    assert result[1].source == ''


def test_fetch_news_empty_cleaned_title_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item whose title is empty after suffix removal is dropped (E-6)."""
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_EMPTY_TITLE_XML),
        ),
        patch('time.sleep'),
    ):
        result = fetch_news('AAPL', 'US')

    assert result == []


def test_fetch_news_http_timeout_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            side_effect=httpx.TimeoutException('timed out'),
        ),
        patch('time.sleep'),
    ):
        result = fetch_news('AAPL', 'US')

    assert result == []
    fake_cache.put.assert_not_called()


def test_fetch_news_http_status_error_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        '503', request=MagicMock(), response=MagicMock()
    )

    with (
        patch('fastapistock.repositories.news_repo.httpx.get', return_value=resp),
        patch('time.sleep'),
    ):
        result = fetch_news('AAPL', 'US')

    assert result == []


def test_fetch_news_broken_xml_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response('<rss><channel><item>broken'),
        ),
        patch('time.sleep'),
    ):
        result = fetch_news('2330', 'TW')

    assert result == []


def test_fetch_news_empty_cache_falls_through_to_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit with items=[] must fall through to HTTP (stale-cache bypass)."""
    fake_cache = MagicMock()
    fake_cache.get.return_value = {'items': []}  # stale empty entry
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_XML),
        ) as mock_get,
        patch('time.sleep'),
    ):
        result = fetch_news('2330', 'TW')

    mock_get.assert_called_once()
    assert result[0].title == '台積電法說會釋利多'
    fake_cache.put.assert_called_once()


def test_fetch_news_zero_items_cached_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RSS with 0 items returns [] and caches an empty payload (E-4)."""
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_NO_ITEMS_XML),
        ),
        patch('time.sleep'),
    ):
        result = fetch_news('AAPL', 'US')

    assert result == []
    assert fake_cache.put.call_args[0][1] == {'items': []}


def test_fetch_news_tw_query_uses_chinese_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch('twstock.codes', {'2330': SimpleNamespace(name='台積電')}),
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_XML),
        ) as mock_get,
        patch('time.sleep'),
    ):
        fetch_news('2330', 'TW')

    params = mock_get.call_args.kwargs['params']
    assert params['q'] == '台積電'
    assert params['hl'] == 'zh-TW'
    assert params['gl'] == 'TW'
    assert params['ceid'] == 'TW:zh-Hant'


def test_fetch_news_tw_query_falls_back_when_code_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown TW code falls back to '{symbol} 股票' (E-13)."""
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch('twstock.codes', {}),
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_XML),
        ) as mock_get,
        patch('time.sleep'),
    ):
        fetch_news('9999', 'TW')

    assert mock_get.call_args.kwargs['params']['q'] == '9999 股票'


def test_fetch_news_us_query_uses_symbol_stock_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_XML),
        ) as mock_get,
        patch('time.sleep'),
    ):
        fetch_news('AAPL', 'US')

    assert mock_get.call_args.kwargs['params']['q'] == 'AAPL 股票'


def test_fetch_news_cache_key_is_v2_and_date_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache key must carry the v2 prefix and today's date."""
    from datetime import date

    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(_RSS_NO_ITEMS_XML),
        ),
        patch('time.sleep'),
    ):
        fetch_news('AAPL', 'US')

    today = date.today().isoformat()
    expected_key = f'news:v2:US:AAPL:{today}'
    assert fake_cache.get.call_args[0][0] == expected_key
    assert fake_cache.put.call_args[0][0] == expected_key


def test_fetch_news_caps_items_at_five(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    item_xml = (
        '<item><title>新聞 {i}</title><link>https://news.google.com/{i}</link></item>'
    )
    xml = (
        '<rss version="2.0"><channel>'
        + ''.join(item_xml.format(i=i) for i in range(8))
        + '</channel></rss>'
    )

    with (
        patch(
            'fastapistock.repositories.news_repo.httpx.get',
            return_value=_make_response(xml),
        ),
        patch('time.sleep'),
    ):
        result = fetch_news('AAPL', 'US')

    assert len(result) == 5
