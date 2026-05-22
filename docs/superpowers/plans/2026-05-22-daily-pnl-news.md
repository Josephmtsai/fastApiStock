# Daily P&L + News Sentiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance `/pnl` with per-stock daily P&L breakdown and keyword-based news sentiment, plus post-market scheduled push.

**Architecture:** Three new modules (`news_repo`, `news_service`, `pnl_service`) follow the existing repository → service layering. `pnl_service.build_pnl_report()` is the single public entry point consumed by both the webhook and the scheduler. The existing `portfolio_service.get_pnl_reply()` is left intact; only the webhook dispatch is rerouted.

**Tech Stack:** FastAPI, yfinance (news), Redis (cache), APScheduler (cron), python-telegram-bot-api via httpx, MarkdownV2 escaping.

---

## File Map

| Action | Path |
|--------|------|
| Create | `src/fastapistock/repositories/news_repo.py` |
| Create | `src/fastapistock/services/news_service.py` |
| Create | `src/fastapistock/services/pnl_service.py` |
| Modify | `src/fastapistock/routers/webhook.py` (lines ~251-255) |
| Modify | `src/fastapistock/scheduler.py` (add two cron jobs) |
| Create | `tests/test_news_repo.py` |
| Create | `tests/test_news_service.py` |
| Create | `tests/test_pnl_service.py` |
| Modify | `tests/test_webhook.py` |
| Modify | `tests/test_scheduler.py` |

---

## Task 1: news_repo.py — Fetch + Cache News

**Files:**
- Create: `src/fastapistock/repositories/news_repo.py`
- Create: `tests/test_news_repo.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_news_repo.py
from unittest.mock import MagicMock, patch

import pytest

from fastapistock.repositories.news_repo import NewsItem, fetch_news


def _make_cache_miss() -> MagicMock:
    m = MagicMock()
    m.get.return_value = None
    return m


def test_fetch_news_cache_hit_skips_yfinance(monkeypatch):
    cached = {'items': [{'title': 'Good news', 'url': 'http://x.com'}]}
    fake_cache = MagicMock()
    fake_cache.get.return_value = cached
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with patch('yfinance.Ticker') as mock_ticker:
        result = fetch_news('AAPL', 'US')

    mock_ticker.assert_not_called()
    assert result == [NewsItem(title='Good news', url='http://x.com')]


def test_fetch_news_cache_miss_calls_yfinance(monkeypatch):
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    mock_ticker = MagicMock()
    mock_ticker.news = [{'title': 'Breaking', 'link': 'http://y.com'}]

    with patch('yfinance.Ticker', return_value=mock_ticker):
        with patch('time.sleep'):
            result = fetch_news('AAPL', 'US')

    assert result == [NewsItem(title='Breaking', url='http://y.com')]
    fake_cache.put.assert_called_once()


def test_fetch_news_yfinance_exception_returns_empty(monkeypatch):
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    with patch('yfinance.Ticker', side_effect=Exception('network error')):
        with patch('time.sleep'):
            result = fetch_news('2330', 'TW')

    assert result == []


def test_fetch_news_tw_uses_tw_suffix(monkeypatch):
    fake_cache = _make_cache_miss()
    monkeypatch.setattr('fastapistock.repositories.news_repo._cache', fake_cache)

    captured = {}

    def fake_ticker(sym):
        captured['sym'] = sym
        m = MagicMock()
        m.news = []
        return m

    with patch('yfinance.Ticker', side_effect=fake_ticker):
        with patch('time.sleep'):
            fetch_news('2330', 'TW')

    assert captured['sym'] == '2330.TW'
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_news_repo.py -v
```
Expected: `ModuleNotFoundError` or `ImportError` (file doesn't exist yet)

- [ ] **Step 3: Create news_repo.py**

```python
# src/fastapistock/repositories/news_repo.py
"""Repository for fetching stock news from Yahoo Finance."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Literal

import yfinance as yf

from fastapistock.cache import redis_cache as _cache

logger = logging.getLogger(__name__)

_CACHE_TTL = 4 * 60 * 60  # 4 hours
_MAX_FETCH = 5             # fetch up to 5; service trims to max_items


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
    cache_key = f'news:{market}:{symbol}'
    cached = _cache.get(cache_key)
    if cached is not None:
        raw_items = cached.get('items', [])
        return [NewsItem(title=i['title'], url=i['url']) for i in raw_items]

    time.sleep(random.uniform(0.5, 1.5))

    ticker_sym = f'{symbol}.TW' if market == 'TW' else symbol
    try:
        raw_news: list[dict[str, object]] = yf.Ticker(ticker_sym).news or []
    except Exception as exc:
        logger.warning('News fetch failed for %s: %s', symbol, exc)
        return []

    items = [
        NewsItem(title=str(n.get('title', '')), url=str(n.get('link', '')))
        for n in raw_news[:_MAX_FETCH]
        if n.get('title')
    ]

    _cache.put(
        cache_key,
        {'items': [{'title': i.title, 'url': i.url} for i in items]},
        _CACHE_TTL,
    )
    return items
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_news_repo.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```
git add src/fastapistock/repositories/news_repo.py tests/test_news_repo.py
git commit -m "feat: add news_repo with Redis cache and yfinance fetch"
```

---

## Task 2: news_service.py — Keyword Sentiment Classification

**Files:**
- Create: `src/fastapistock/services/news_service.py`
- Create: `tests/test_news_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_news_service.py
from unittest.mock import patch

import pytest

from fastapistock.services.news_service import (
    SentimentNews,
    classify_sentiment,
    get_sentiment_news,
)
from fastapistock.repositories.news_repo import NewsItem


@pytest.mark.parametrize('title,expected', [
    ('AI晶片需求強勁，台積電Q2展望樂觀', '正面'),
    ('外資連續買超3日', '正面'),
    ('Apple beat expectations', '正面'),
    ('Stock surged 5%', '正面'),
    ('iPhone銷量下滑，分析師下修評等', '負面'),
    ('Company reported a loss', '負面'),
    ('Analyst downgrade issued', '負面'),
    ('Apple reports quarterly results', '中性'),
    ('市場今日交易平穩', '中性'),
])
def test_classify_sentiment(title, expected):
    assert classify_sentiment(title) == expected


def test_get_sentiment_news_returns_max_items():
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


def test_get_sentiment_news_empty_returns_empty():
    with patch('fastapistock.services.news_service.fetch_news', return_value=[]):
        result = get_sentiment_news('2330', 'TW')
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_news_service.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Create news_service.py**

```python
# src/fastapistock/services/news_service.py
"""Keyword-based sentiment classification for stock news headlines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapistock.repositories.news_repo import NewsItem, fetch_news

Sentiment = Literal['正面', '中性', '負面']

_POSITIVE: frozenset[str] = frozenset([
    '強勁', '樂觀', '買超', '創高', '成長', '上漲', '突破', '獲利', '亮眼',
    'beat', 'surge', 'rally', 'gain', 'rise', 'strong', 'upgrade',
])
_NEGATIVE: frozenset[str] = frozenset([
    '下滑', '虧損', '賣超', '暴跌', '警告', '下跌', '跌破', '衰退', '下修',
    'miss', 'drop', 'decline', 'downgrade', 'fall', 'loss', 'weak', 'cut',
])


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
    news = fetch_news(symbol, market)
    return [
        SentimentNews(title=item.title, sentiment=classify_sentiment(item.title))
        for item in news[:max_items]
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_news_service.py -v
```
Expected: 11 passed

- [ ] **Step 5: Commit**

```
git add src/fastapistock/services/news_service.py tests/test_news_service.py
git commit -m "feat: add news_service with keyword sentiment classification"
```

---

## Task 3: pnl_service.py — Core P&L Calculation

**Files:**
- Create: `src/fastapistock/services/pnl_service.py`
- Create: `tests/test_pnl_service.py`

- [ ] **Step 1: Write failing tests (calculation only)**

```python
# tests/test_pnl_service.py
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from fastapistock.schemas.stock import RichStockData
from fastapistock.services.pnl_service import (
    _calc_market_today_pnl,
    _held_stocks,
)


def _make_rich(
    symbol: str,
    market: str,
    price: float = 100.0,
    prev_close: float = 95.0,
    change: float = 5.0,
    change_pct: float = 5.26,
    shares: int | None = 100,
    avg_cost: float | None = 80.0,
    unrealized_pnl: float | None = 2000.0,
) -> RichStockData:
    return RichStockData(
        symbol=symbol,
        display_name=symbol,
        market=market,  # type: ignore[arg-type]
        price=price,
        prev_close=prev_close,
        change=change,
        change_pct=change_pct,
        ma20=90.0,
        volume=1000,
        volume_avg20=900,
        shares=shares,
        avg_cost=avg_cost,
        unrealized_pnl=unrealized_pnl,
    )


def test_held_stocks_filters_none_shares():
    stocks = [
        _make_rich('A', 'TW', shares=100),
        _make_rich('B', 'TW', shares=None),
        _make_rich('C', 'TW', shares=0),
    ]
    result = _held_stocks(stocks)
    assert [s.symbol for s in result] == ['A']


def test_calc_market_today_pnl_sums_change_times_shares():
    stocks = [
        _make_rich('A', 'TW', change=5.0, shares=200),
        _make_rich('B', 'TW', change=-3.0, shares=100),
    ]
    total = _calc_market_today_pnl(stocks)
    assert total == pytest.approx(5.0 * 200 + (-3.0) * 100)


def test_calc_market_today_pnl_empty_returns_zero():
    assert _calc_market_today_pnl([]) == pytest.approx(0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_pnl_service.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Create pnl_service.py with calculation helpers**

```python
# src/fastapistock/services/pnl_service.py
"""Service for building the daily P&L + news sentiment Telegram report."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapistock.schemas.stock import RichStockData

logger = logging.getLogger(__name__)

_MSG_LIMIT = 4096


def _held_stocks(stocks: list[RichStockData]) -> list[RichStockData]:
    """Return only stocks with a positive share count."""
    return [s for s in stocks if s.shares is not None and s.shares > 0]


def _calc_market_today_pnl(stocks: list[RichStockData]) -> float:
    """Sum today's P&L across held stocks: change × shares."""
    return sum(s.change * (s.shares or 0) for s in stocks)
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_pnl_service.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```
git add src/fastapistock/services/pnl_service.py tests/test_pnl_service.py
git commit -m "feat: add pnl_service calculation helpers"
```

---

## Task 4: pnl_service.py — Message Formatting + build_pnl_report

**Files:**
- Modify: `src/fastapistock/services/pnl_service.py`
- Modify: `tests/test_pnl_service.py`

- [ ] **Step 1: Write failing tests for message formatting**

Append to `tests/test_pnl_service.py`:

```python
from fastapistock.services.pnl_service import build_pnl_report, _split_message


def test_split_message_short_message_not_split():
    msg = 'Hello world'
    assert _split_message(msg) == ['Hello world']


def test_split_message_long_message_splits_at_newline():
    line = 'A' * 100 + '\n'
    msg = line * 50  # 5050 chars > 4096
    parts = _split_message(msg)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= _MSG_LIMIT


def test_build_pnl_report_returns_list_of_strings():
    tw_stock = _make_rich('2330', 'TW', change=15.0, shares=1000,
                          unrealized_pnl=45000.0)
    us_stock = _make_rich('AAPL', 'US', change=-3.2, shares=10,
                          unrealized_pnl=-800.0)

    with patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr, \
         patch('fastapistock.services.pnl_service.stock_service') as mock_ss, \
         patch('fastapistock.services.pnl_service.us_stock_service') as mock_us, \
         patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]):
        mock_pr.fetch_portfolio.return_value = {'2330': MagicMock()}
        mock_pr.fetch_portfolio_us.return_value = {'AAPL': MagicMock()}
        mock_ss.get_rich_tw_stocks.return_value = [tw_stock]
        mock_us.get_us_stocks.return_value = [us_stock]

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    assert isinstance(result, list)
    assert len(result) >= 1
    full = '\n'.join(result)
    assert '2026-05-22' in full
    assert '2330' in full
    assert 'AAPL' in full


def test_build_pnl_report_tw_fetch_failure_shows_error():
    with patch('fastapistock.services.pnl_service.portfolio_repo') as mock_pr, \
         patch('fastapistock.services.pnl_service.stock_service') as mock_ss, \
         patch('fastapistock.services.pnl_service.us_stock_service') as mock_us, \
         patch('fastapistock.services.pnl_service.get_sentiment_news', return_value=[]):
        mock_pr.fetch_portfolio.side_effect = Exception('sheets down')
        mock_pr.fetch_portfolio_us.return_value = {}
        mock_us.get_us_stocks.return_value = []

        now = datetime(2026, 5, 22, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))
        result = build_pnl_report(now)

    full = '\n'.join(result)
    assert '資料讀取失敗' in full
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_pnl_service.py::test_build_pnl_report_returns_list_of_strings -v
```
Expected: `ImportError` (build_pnl_report not yet defined)

- [ ] **Step 3: Complete pnl_service.py**

Replace `src/fastapistock/services/pnl_service.py` with:

```python
# src/fastapistock/services/pnl_service.py
"""Service for building the daily P&L + news sentiment Telegram report."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Literal

from fastapistock.repositories import portfolio_repo
from fastapistock.schemas.stock import RichStockData
from fastapistock.services import stock_service, us_stock_service
from fastapistock.services.news_service import get_sentiment_news

logger = logging.getLogger(__name__)

_MSG_LIMIT = 4096
_MD_SPECIAL = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')


def _esc(text: str) -> str:
    return _MD_SPECIAL.sub(r'\\\1', text)


def _held_stocks(stocks: list[RichStockData]) -> list[RichStockData]:
    return [s for s in stocks if s.shares is not None and s.shares > 0]


def _calc_market_today_pnl(stocks: list[RichStockData]) -> float:
    return sum(s.change * (s.shares or 0) for s in stocks)


def _fmt_tw_amount(amount: float) -> str:
    sign = '+' if amount >= 0 else ''
    return f'{sign}NT${amount:,.0f}'


def _fmt_us_amount(amount: float) -> str:
    sign = '+' if amount >= 0 else ''
    return f'{sign}US${amount:,.2f}'


def _split_message(text: str) -> list[str]:
    """Split *text* into segments of at most _MSG_LIMIT chars, breaking at newlines."""
    if len(text) <= _MSG_LIMIT:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > _MSG_LIMIT and current:
            parts.append(''.join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        parts.append(''.join(current))
    return parts


def _build_stock_row(
    stock: RichStockData,
    market: Literal['TW', 'US'],
) -> str:
    """Build a MarkdownV2 row for one held stock."""
    lines: list[str] = []

    name = _esc(stock.display_name) if stock.display_name != stock.symbol else ''
    header = f'*{_esc(stock.symbol)}*' + (f' {name}' if name else '')
    lines.append(header)

    change_sign = '+' if stock.change >= 0 else ''
    price_line = (
        f'現價 {_esc(str(round(stock.price, 2)))} \\| '
        f'今日 {_esc(f"{change_sign}{round(stock.change, 2)}")} '
        f'\\({_esc(f"{change_sign}{round(stock.change_pct, 2)}%")}\\)'
    )
    lines.append(price_line)

    if stock.unrealized_pnl is not None:
        if market == 'TW':
            pnl_str = _fmt_tw_amount(stock.unrealized_pnl)
        else:
            pnl_str = _fmt_us_amount(stock.unrealized_pnl)
        lines.append(f'持倉損益 {_esc(pnl_str)}')

    try:
        news_items = get_sentiment_news(stock.symbol, market)
        for item in news_items:
            lines.append(f'📰 {_esc(item.title)} \\[{_esc(item.sentiment)}\\]')
    except Exception as exc:
        logger.warning('News fetch failed for %s: %s', stock.symbol, exc)
        lines.append('📰 暫無新聞')

    return '\n'.join(lines)


def _build_market_section(
    stocks: list[RichStockData],
    market: Literal['TW', 'US'],
) -> str:
    held = _held_stocks(stocks)
    flag = '🇹🇼 台股明細' if market == 'TW' else '🇺🇸 美股明細'
    if not held:
        label = '目前無持股' if market == 'TW' else 'No holdings'
        return f'\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n{flag}\n\n{label}'
    rows = '\n\n'.join(_build_stock_row(s, market) for s in held)
    return f'\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n{flag}\n\n{rows}'


def build_pnl_report(now: datetime) -> list[str]:
    """Build the daily P&L + news report as a list of MarkdownV2 message segments.

    Args:
        now: Current datetime in Asia/Taipei timezone.

    Returns:
        List of MarkdownV2 strings, each at most 4096 chars.
    """
    date_str = now.strftime('%Y\\-%m\\-%d')
    sections: list[str] = [f'📊 *每日損益報告 {date_str}*']

    # --- TW ---
    try:
        tw_symbols = list(portfolio_repo.fetch_portfolio().keys())
        tw_stocks = stock_service.get_rich_tw_stocks(tw_symbols) if tw_symbols else []
    except Exception as exc:
        logger.error('TW portfolio fetch failed: %s', exc)
        tw_stocks = None

    # --- US ---
    try:
        us_symbols = list(portfolio_repo.fetch_portfolio_us().keys())
        us_stocks = us_stock_service.get_us_stocks(us_symbols) if us_symbols else []
    except Exception as exc:
        logger.error('US portfolio fetch failed: %s', exc)
        us_stocks = None

    # --- Account summary ---
    tw_today = _calc_market_today_pnl(_held_stocks(tw_stocks)) if tw_stocks else None
    us_today = _calc_market_today_pnl(_held_stocks(us_stocks)) if us_stocks else None

    tw_line = (
        f'🇹🇼 台股今日：{_esc(_fmt_tw_amount(tw_today))}' if tw_today is not None
        else '🇹🇼 台股：資料讀取失敗'
    )
    us_line = (
        f'🇺🇸 美股今日：{_esc(_fmt_us_amount(us_today))}' if us_today is not None
        else '🇺🇸 美股：資料讀取失敗'
    )
    sections.append(f'💰 *帳戶總覽*\n{tw_line}\n{us_line}')

    # --- Stock sections ---
    if tw_stocks is not None:
        sections.append(_build_market_section(tw_stocks, 'TW'))
    else:
        sections.append('\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n🇹🇼 台股明細\n\n資料讀取失敗')

    if us_stocks is not None:
        sections.append(_build_market_section(us_stocks, 'US'))
    else:
        sections.append('\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n🇺🇸 美股明細\n\n資料讀取失敗')

    full_text = '\n\n'.join(sections)
    return _split_message(full_text)
```

- [ ] **Step 4: Run all pnl_service tests**

```
uv run pytest tests/test_pnl_service.py -v
```
Expected: all passed

- [ ] **Step 5: Commit**

```
git add src/fastapistock/services/pnl_service.py tests/test_pnl_service.py
git commit -m "feat: add pnl_service with P&L calculation and MarkdownV2 report"
```

---

## Task 5: webhook.py — Update /pnl Dispatch

**Files:**
- Modify: `src/fastapistock/routers/webhook.py`
- Modify: `tests/test_webhook.py`

- [ ] **Step 1: Write failing test**

Find existing `/pnl` tests in `tests/test_webhook.py` and add or update:

```python
# Add to tests/test_webhook.py
def test_pnl_command_calls_pnl_service_and_sends_markdownv2(client, monkeypatch):
    """Verify /pnl dispatches to pnl_service and sends MarkdownV2."""
    monkeypatch.setattr(
        'fastapistock.routers.webhook.build_pnl_report',
        lambda now: ['segment1', 'segment2'],
    )
    sent = []
    monkeypatch.setattr(
        'fastapistock.routers.webhook.reply_to_chat',
        lambda chat_id, text, **kw: sent.append((chat_id, text, kw)),
    )

    payload = {
        'update_id': 1,
        'message': {
            'message_id': 1,
            'from': {'id': 111, 'is_bot': False, 'first_name': 'Joe'},
            'chat': {'id': 111},
            'text': '/pnl',
        },
    }
    headers = {'X-Telegram-Bot-Api-Secret-Token': 'test-secret'}
    resp = client.post('/api/v1/webhook/telegram', json=payload, headers=headers)
    assert resp.status_code == 200
    assert len(sent) == 2
    assert sent[0][2].get('parse_mode') == 'MarkdownV2'
    assert sent[1][2].get('parse_mode') == 'MarkdownV2'
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_webhook.py::test_pnl_command_calls_pnl_service_and_sends_markdownv2 -v
```
Expected: FAIL (current dispatch uses portfolio_service, not pnl_service)

- [ ] **Step 3: Update webhook.py /pnl dispatch**

In `src/fastapistock/routers/webhook.py`, locate the `/pnl` branch (~line 251) and replace:

```python
# BEFORE
elif cmd == '/pnl':
    from fastapistock.services.portfolio_service import get_pnl_reply

    reply = get_pnl_reply()
```

With:

```python
# AFTER
elif cmd == '/pnl':
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fastapistock.services.pnl_service import build_pnl_report

    segments = build_pnl_report(datetime.now(ZoneInfo('Asia/Taipei')))
    for segment in segments:
        reply_to_chat(chat_id, segment, parse_mode='MarkdownV2')
    return
```

- [ ] **Step 4: Run test to verify it passes**

```
uv run pytest tests/test_webhook.py::test_pnl_command_calls_pnl_service_and_sends_markdownv2 -v
```
Expected: PASS

- [ ] **Step 5: Run full webhook test suite to ensure no regressions**

```
uv run pytest tests/test_webhook.py -v
```
Expected: all passed

- [ ] **Step 6: Commit**

```
git add src/fastapistock/routers/webhook.py tests/test_webhook.py
git commit -m "feat: update /pnl webhook to use pnl_service with MarkdownV2"
```

---

## Task 6: scheduler.py — Post-Market Cron Jobs

**Files:**
- Modify: `src/fastapistock/scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_scheduler.py
from unittest.mock import MagicMock, call, patch

def test_push_daily_pnl_sends_all_segments(monkeypatch):
    """push_daily_pnl must send every segment from build_pnl_report."""
    from fastapistock.scheduler import push_daily_pnl
    from zoneinfo import ZoneInfo
    from datetime import datetime

    monkeypatch.setattr('fastapistock.scheduler.TELEGRAM_USER_ID', '999')

    sent = []
    monkeypatch.setattr(
        'fastapistock.services.telegram_service.send_text_message',
        lambda uid, text, **kw: sent.append((uid, text, kw)),
    )
    with patch('fastapistock.scheduler.build_pnl_report', return_value=['seg1', 'seg2']):
        push_daily_pnl()

    assert len(sent) == 2
    assert all(kw.get('parse_mode') == 'MarkdownV2' for _, _, kw in sent)


def test_push_daily_pnl_no_user_id_skips(monkeypatch):
    from fastapistock.scheduler import push_daily_pnl
    monkeypatch.setattr('fastapistock.scheduler.TELEGRAM_USER_ID', '')
    with patch('fastapistock.scheduler.build_pnl_report') as mock_build:
        push_daily_pnl()
    mock_build.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_scheduler.py::test_push_daily_pnl_sends_all_segments -v
```
Expected: `ImportError` (push_daily_pnl not yet defined)

- [ ] **Step 3: Add push_daily_pnl function to scheduler.py**

In `src/fastapistock/scheduler.py`, add after the existing push functions:

```python
def push_daily_pnl() -> None:
    """Build and send the daily P&L + news report to the configured Telegram user.

    Called by both the TW close job (14:35) and the US close job (04:05 next day).
    """
    if not TELEGRAM_USER_ID:
        logger.warning('TELEGRAM_USER_ID not set; skipping daily PnL push')
        return
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from fastapistock.services.pnl_service import build_pnl_report
        from fastapistock.services.telegram_service import send_text_message

        now = datetime.now(ZoneInfo('Asia/Taipei'))
        segments = build_pnl_report(now)
        for segment in segments:
            send_text_message(TELEGRAM_USER_ID, segment, parse_mode='MarkdownV2')
        logger.info('Daily PnL push complete: %d segments sent', len(segments))
    except Exception:
        logger.exception('Daily PnL push failed')
```

- [ ] **Step 4: Register the two cron jobs in create_scheduler()**

Find the `create_scheduler()` function in `scheduler.py` and add before the `scheduler.start()` call:

```python
# TW close: weekdays 14:35 Taipei
scheduler.add_job(
    push_daily_pnl,
    CronTrigger(hour=14, minute=35, day_of_week='mon-fri', timezone=_TZ),
    id='daily_pnl_tw',
    replace_existing=True,
)
# US close: Tue–Sat 04:05 Taipei (Mon–Fri US Eastern close)
scheduler.add_job(
    push_daily_pnl,
    CronTrigger(hour=4, minute=5, day_of_week='tue-sat', timezone=_TZ),
    id='daily_pnl_us',
    replace_existing=True,
)
```

- [ ] **Step 5: Run scheduler tests**

```
uv run pytest tests/test_scheduler.py -v
```
Expected: all passed

- [ ] **Step 6: Commit**

```
git add src/fastapistock/scheduler.py tests/test_scheduler.py
git commit -m "feat: add post-market daily PnL push jobs to scheduler"
```

---

## Final: Full Test Suite

- [ ] **Run all tests and verify no regressions**

```
uv run pytest -x -q
```
Expected: all tests pass (was 599 passed, 1 skipped at baseline)

- [ ] **Run linting and type checking**

```
uv run ruff check . --fix && uv run ruff format . && uv run mypy src/
```
Expected: exit 0

- [ ] **Final commit if any lint fixes**

```
git add -u
git commit -m "chore: fix lint/type issues in spec 012 implementation"
```

---

## Self-Review Notes

1. **Spec coverage:**
   - AC1 ✓ (account summary in build_pnl_report)
   - AC2, AC3 ✓ (_build_stock_row per market)
   - AC4 ✓ (get_sentiment_news in _build_stock_row)
   - AC5 ✓ (scheduler cron jobs)
   - AC6 ✓ (APScheduler day_of_week constraint)
   - AC7 ✓ (_split_message)
   - AC8 ✓ (try/except with fallback text in build_pnl_report)

2. **Type consistency:** `_held_stocks`, `_calc_market_today_pnl`, `build_pnl_report` all use `list[RichStockData]` consistently.

3. **No placeholders:** All code blocks are complete and runnable.

4. **Breaking change note:** The `/pnl` webhook dispatch is rerouted from `portfolio_service.get_pnl_reply()` to `pnl_service.build_pnl_report()`. The old `portfolio_service.get_pnl_reply()` is NOT deleted — it is still used by any tests or other callers. The message format changes from plain text to MarkdownV2.
