"""Tests for US stock service (cache + parallel fetch)."""

from unittest.mock import MagicMock, patch

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
