"""Tests for the portfolio Redis cache layer in stock_service."""

from unittest.mock import MagicMock, patch

from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.services.stock_service import _get_cached_portfolio

_ENTRY = PortfolioEntry(
    symbol='2330', shares=1000, avg_cost=820.0, unrealized_pnl=75000.0
)
_PORTFOLIO = {'2330': _ENTRY}

_SERIALISED = {
    '2330': {
        'symbol': '2330',
        'shares': 1000,
        'avg_cost': 820.0,
        'unrealized_pnl': 75000.0,
    }
}


def _mock_cache(get_return: object = None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = get_return
    return cache


def test_first_call_fetches_and_stores() -> None:
    """Cache miss → fetch_portfolio() called once, result stored in Redis."""
    mock_cache = _mock_cache(get_return=None)
    with (
        patch('fastapistock.services.stock_service.redis_cache', mock_cache),
        patch(
            'fastapistock.services.stock_service.fetch_portfolio',
            return_value=_PORTFOLIO,
        ) as mock_fetch,
    ):
        result = _get_cached_portfolio()

    mock_fetch.assert_called_once()
    mock_cache.put.assert_called_once()
    assert '2330' in result
    assert result['2330'].avg_cost == 820.0


def test_second_call_uses_cache() -> None:
    """Cache hit → fetch_portfolio() never called."""
    mock_cache = _mock_cache(get_return=_SERIALISED)
    with (
        patch('fastapistock.services.stock_service.redis_cache', mock_cache),
        patch(
            'fastapistock.services.stock_service.fetch_portfolio',
        ) as mock_fetch,
    ):
        result = _get_cached_portfolio()

    mock_fetch.assert_not_called()
    assert '2330' in result
    assert result['2330'].shares == 1000


def test_redis_unavailable_falls_back_to_fetch() -> None:
    """Redis returning None (unavailable/miss) → fetch_portfolio() called, no crash."""
    mock_cache = _mock_cache(get_return=None)
    with (
        patch('fastapistock.services.stock_service.redis_cache', mock_cache),
        patch(
            'fastapistock.services.stock_service.fetch_portfolio',
            return_value=_PORTFOLIO,
        ) as mock_fetch,
    ):
        result = _get_cached_portfolio()

    mock_fetch.assert_called_once()
    assert result == _PORTFOLIO


def test_ttl_expired_refetches() -> None:
    """After TTL expiry, cache.get returns None again → re-fetch triggered."""
    mock_cache = _mock_cache(get_return=None)
    with (
        patch('fastapistock.services.stock_service.redis_cache', mock_cache),
        patch(
            'fastapistock.services.stock_service.fetch_portfolio',
            return_value=_PORTFOLIO,
        ) as mock_fetch,
    ):
        result = _get_cached_portfolio()

    mock_fetch.assert_called_once()
    assert '2330' in result


def test_empty_portfolio_not_cached() -> None:
    """Empty portfolio from Sheets → should not be stored in Redis."""
    mock_cache = _mock_cache(get_return=None)
    with (
        patch('fastapistock.services.stock_service.redis_cache', mock_cache),
        patch(
            'fastapistock.services.stock_service.fetch_portfolio',
            return_value={},
        ),
    ):
        result = _get_cached_portfolio()

    mock_cache.put.assert_not_called()
    assert result == {}
