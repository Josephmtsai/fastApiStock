"""Tests for US stock service (cache + parallel fetch)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.schemas.stock import RichStockData

_STOCK = RichStockData(
    symbol='AAPL',
    display_name='Apple Inc.',
    market='US',
    price=195.5,
    prev_close=193.2,
    change=2.3,
    change_pct=1.19,
    ma20=190.0,
    volume=80_000_000,
    volume_avg20=70_000_000,
)
_US_PORTFOLIO = {
    'AAPL': PortfolioEntry(
        symbol='AAPL',
        shares=0,
        avg_cost=180.0,
        unrealized_pnl=12000.0,
    )
}


@patch('fastapistock.services.us_stock_service.redis_cache')
@patch('fastapistock.services.us_stock_service.fetch_us_stock', return_value=_STOCK)
@patch(
    'fastapistock.services.us_stock_service.fetch_portfolio_us',
    return_value=_US_PORTFOLIO,
)
def test_get_us_stock_cache_miss_fetches_and_stores(
    _mock_portfolio: MagicMock,
    mock_fetch: MagicMock,
    mock_cache: MagicMock,
) -> None:
    from fastapistock.services.us_stock_service import get_us_stock

    mock_cache.get.return_value = None
    result = get_us_stock('AAPL')
    assert result.symbol == 'AAPL'
    mock_fetch.assert_called_once_with('AAPL')
    mock_cache.put.assert_called_once()


@patch('fastapistock.services.us_stock_service.redis_cache')
def test_get_us_stock_cache_hit_returns_cached(mock_cache: MagicMock) -> None:
    from fastapistock.services.us_stock_service import get_us_stock

    mock_cache.get.return_value = _STOCK.model_dump()
    result = get_us_stock('AAPL')
    assert result.symbol == 'AAPL'
    assert result.market == 'US'


@patch('fastapistock.services.us_stock_service.redis_cache')
@patch('fastapistock.services.us_stock_service.fetch_us_stock', return_value=_STOCK)
@patch(
    'fastapistock.services.us_stock_service.fetch_portfolio_us',
    return_value=_US_PORTFOLIO,
)
def test_get_us_stocks_parallel_fetch(
    _mock_portfolio: MagicMock,
    mock_fetch: MagicMock,
    mock_cache: MagicMock,
) -> None:
    from fastapistock.services.us_stock_service import get_us_stocks

    mock_cache.get.return_value = None
    results = get_us_stocks(['AAPL', 'TSLA'])
    assert len(results) == 2
    assert mock_fetch.call_count == 2


@patch('fastapistock.services.us_stock_service.redis_cache')
@patch(
    'fastapistock.services.us_stock_service.fetch_portfolio_us',
    return_value=_US_PORTFOLIO,
)
def test_get_us_stocks_all_cache_hits(
    _mock_portfolio: MagicMock,
    mock_cache: MagicMock,
) -> None:
    from fastapistock.services.us_stock_service import get_us_stocks

    mock_cache.get.side_effect = [_STOCK.model_dump(), None]
    results = get_us_stocks(['AAPL'])
    assert len(results) == 1
    assert results[0].symbol == 'AAPL'


@patch('fastapistock.services.us_stock_service.redis_cache')
@patch(
    'fastapistock.services.us_stock_service.fetch_portfolio_us',
    return_value=_US_PORTFOLIO,
)
def test_get_us_stocks_merges_portfolio_fields(
    mock_portfolio: MagicMock,
    mock_cache: MagicMock,
) -> None:
    from fastapistock.services.us_stock_service import get_us_stocks

    mock_cache.get.side_effect = [None, None, None]
    with patch(
        'fastapistock.services.us_stock_service.fetch_us_stock',
        return_value=_STOCK,
    ):
        results = get_us_stocks(['AAPL'])

    assert results[0].avg_cost == 180.0
    assert results[0].unrealized_pnl == 12000.0
    mock_portfolio.assert_called_once()


@patch('fastapistock.services.us_stock_service.redis_cache')
@patch('fastapistock.services.us_stock_service.fetch_us_stock', return_value=_STOCK)
@patch(
    'fastapistock.services.us_stock_service.fetch_portfolio_us',
    return_value=_US_PORTFOLIO,
)
def test_get_us_stock_cache_put_uses_us_stock_cache_ttl(
    _mock_portfolio: MagicMock,
    mock_fetch: MagicMock,
    mock_cache: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redis_cache.put must be called with the US_STOCK_CACHE_TTL value."""
    # Patch the imported constant in the service module directly so we do not
    # need to reload the module (which would discard the existing @patch mocks).
    monkeypatch.setattr(
        'fastapistock.services.us_stock_service.US_STOCK_CACHE_TTL', 120
    )
    from fastapistock.services.us_stock_service import get_us_stock

    mock_cache.get.return_value = None
    get_us_stock('AAPL')

    mock_cache.put.assert_called_once()
    put_args = mock_cache.put.call_args[0]
    # positional signature: put(key, value, ttl) — third arg is ttl
    assert put_args[2] == 120


# ---------------------------------------------------------------------------
# Task 015-5: Cache key format tests (UTC-hour granularity)
# ---------------------------------------------------------------------------

_PATCH_DATETIME_SVC = 'fastapistock.services.us_stock_service.datetime'


def test_cache_key_format_includes_hour() -> None:
    """UTC frozen to 2026-06-13 14:00 → key is 'us_stock:AAPL:2026-06-13:14'."""
    from fastapistock.services.us_stock_service import _cache_key

    frozen = datetime(2026, 6, 13, 14, 0, 0, tzinfo=UTC)
    with patch(_PATCH_DATETIME_SVC) as mock_dt:
        mock_dt.now.return_value = frozen
        key = _cache_key('AAPL')

    assert key == 'us_stock:AAPL:2026-06-13:14'


def test_cache_key_different_hours_produce_different_keys() -> None:
    """Keys at 09:00 UTC and 10:00 UTC for the same symbol must differ."""
    from fastapistock.services.us_stock_service import _cache_key

    frozen_09 = datetime(2026, 6, 13, 9, 0, 0, tzinfo=UTC)
    frozen_10 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=UTC)

    with patch(_PATCH_DATETIME_SVC) as mock_dt:
        mock_dt.now.return_value = frozen_09
        key_09 = _cache_key('AAPL')

    with patch(_PATCH_DATETIME_SVC) as mock_dt:
        mock_dt.now.return_value = frozen_10
        key_10 = _cache_key('AAPL')

    assert key_09 != key_10


def test_cache_key_midnight_hour_zero() -> None:
    """UTC midnight (hour=0) must produce a key ending with ':0' (no zero-padding)."""
    from fastapistock.services.us_stock_service import _cache_key

    frozen = datetime(2026, 6, 14, 0, 0, 0, tzinfo=UTC)
    with patch(_PATCH_DATETIME_SVC) as mock_dt:
        mock_dt.now.return_value = frozen
        key = _cache_key('AAPL')

    assert key == 'us_stock:AAPL:2026-06-14:0'


# ---------------------------------------------------------------------------
# QA-added: Cache key symbol isolation — different symbols must not share a key
# ---------------------------------------------------------------------------


def test_cache_key_different_symbols_produce_different_keys() -> None:
    """Same UTC hour but different symbols must produce different cache keys."""
    from fastapistock.services.us_stock_service import _cache_key

    frozen = datetime(2026, 6, 13, 14, 0, 0, tzinfo=UTC)
    with patch(_PATCH_DATETIME_SVC) as mock_dt:
        mock_dt.now.return_value = frozen
        key_aapl = _cache_key('AAPL')
        key_tsla = _cache_key('TSLA')

    assert key_aapl != key_tsla
    assert 'AAPL' in key_aapl
    assert 'TSLA' in key_tsla
