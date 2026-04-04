"""Integration tests for the stock quotes endpoint."""

from collections.abc import Callable
from unittest.mock import _patch, patch

import pytest
from fastapi.testclient import TestClient

from fastapistock.main import app
from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.schemas.stock import StockData

client = TestClient(app)

_MOCK_0050 = StockData(
    Name='0050',
    price=185.50,
    ma20=183.20,
    ma60=178.10,
    LastDayPrice=184.00,
    Volume=12345678,
)

_MOCK_2330 = StockData(
    Name='2330',
    price=920.00,
    ma20=915.50,
    ma60=900.00,
    LastDayPrice=918.00,
    Volume=98765432,
)


@pytest.fixture(autouse=True)
def _no_file_cache(tmp_path, monkeypatch):
    """Redirect file cache to a temp directory and always report miss."""
    import fastapistock.cache.file_cache as fc

    monkeypatch.setattr(fc, '_CACHE_ROOT', tmp_path)


def _patch_fetch(
    side_effect: Callable[[str], StockData] | Exception | type[Exception],
) -> _patch:  # type: ignore[type-arg]
    """Return a context manager that patches fetch_stock where it is used."""
    return patch(
        'fastapistock.services.stock_service.fetch_stock',
        side_effect=side_effect,
    )


class TestGetSingleStock:
    def test_success_returns_envelope(self):
        with _patch_fetch(lambda code: _MOCK_0050):
            response = client.get('/api/v1/stock/0050')

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'success'
        assert body['message'] == ''
        assert len(body['data']) == 1

    def test_response_fields(self):
        with _patch_fetch(lambda code: _MOCK_0050):
            body = client.get('/api/v1/stock/0050').json()

        item = body['data'][0]
        assert item['Name'] == '0050'
        assert item['price'] == 185.50
        assert item['ma20'] == 183.20
        assert item['ma60'] == 178.10
        assert item['LastDayPrice'] == 184.00
        assert item['Volume'] == 12345678

    def test_not_found_returns_404(self):
        with _patch_fetch(
            side_effect=StockNotFoundError("No data found for symbol '9999'")
        ):
            response = client.get('/api/v1/stock/9999')

        assert response.status_code == 404
        body = response.json()
        assert body['status'] == 'error'
        assert '9999' in body['message']
        assert body['data'] is None


class TestGetMultipleStocks:
    def _mock_fetch(self, code: str) -> StockData:
        mapping = {'0050': _MOCK_0050, '2330': _MOCK_2330}
        if code not in mapping:
            raise StockNotFoundError(f"No data found for symbol '{code}'")
        return mapping[code]

    def test_two_stocks_returned_in_order(self):
        with _patch_fetch(self._mock_fetch):
            response = client.get('/api/v1/stock/0050,2330')

        assert response.status_code == 200
        data = response.json()['data']
        assert len(data) == 2
        assert data[0]['Name'] == '0050'
        assert data[1]['Name'] == '2330'

    def test_whitespace_around_codes_is_ignored(self):
        with _patch_fetch(self._mock_fetch):
            response = client.get('/api/v1/stock/0050, 2330')

        assert response.status_code == 200
        assert len(response.json()['data']) == 2

    def test_one_invalid_code_returns_404(self):
        with _patch_fetch(self._mock_fetch):
            response = client.get('/api/v1/stock/0050,9999')

        assert response.status_code == 404
        assert response.json()['status'] == 'error'


class TestCacheBehaviour:
    def test_cache_hit_skips_fetch(self):
        call_count = 0

        def counting_fetch(code: str) -> StockData:
            nonlocal call_count
            call_count += 1
            return _MOCK_0050

        with _patch_fetch(counting_fetch):
            client.get('/api/v1/stock/0050')
            client.get('/api/v1/stock/0050')

        # Second request should be served from the file cache (same day key)
        assert call_count == 1
