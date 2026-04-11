"""Unit tests for portfolio_repo PnL cell-reading functions."""

from unittest.mock import MagicMock, patch

import pytest

from fastapistock.repositories.portfolio_repo import fetch_pnl_tw, fetch_pnl_us

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_csv_rows() -> str:
    """Build a minimal CSV where row 18 col 8 = 1234567 and row 20 col 7 = 890123."""
    rows = []
    for i in range(22):
        cols = ['0'] * 10
        if i == 18:
            cols[8] = '1234567'
        if i == 20:
            cols[7] = '890123'
        rows.append(','.join(cols))
    return '\n'.join(rows)


# ---------------------------------------------------------------------------
# fetch_pnl_tw
# ---------------------------------------------------------------------------


class TestFetchPnlTw:
    def test_returns_cached_float_on_cache_hit(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get.return_value = {'value': '1234567.0'}

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_TW = 'gid_tw'
            result = fetch_pnl_tw()

        assert result == pytest.approx(1234567.0)
        mock_cache.get.assert_called_once()

    def test_fetches_live_on_cache_miss_and_caches_result(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        csv_text = _make_csv_rows()

        mock_response = MagicMock()
        mock_response.text = csv_text
        mock_response.raise_for_status = MagicMock()

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
            patch(
                'fastapistock.repositories.portfolio_repo.httpx.get',
                return_value=mock_response,
            ),
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_TW = 'gid_tw'
            mock_cfg.PORTFOLIO_CACHE_TTL = 3600
            result = fetch_pnl_tw()

        assert result == pytest.approx(1234567.0)
        mock_cache.put.assert_called_once()

    def test_returns_none_on_http_error(self) -> None:
        import httpx as _httpx

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
            patch(
                'fastapistock.repositories.portfolio_repo.httpx.get',
                side_effect=_httpx.RequestError('timeout'),
            ),
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_TW = 'gid_tw'
            result = fetch_pnl_tw()

        assert result is None

    def test_returns_none_when_config_missing(self) -> None:
        with patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg:
            mock_cfg.GOOGLE_SHEETS_ID = ''
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_TW = ''
            result = fetch_pnl_tw()

        assert result is None

    def test_returns_none_when_row_out_of_range(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        mock_response = MagicMock()
        mock_response.text = 'a,b,c\n1,2,3\n'  # only 2 rows, need row 19
        mock_response.raise_for_status = MagicMock()

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
            patch(
                'fastapistock.repositories.portfolio_repo.httpx.get',
                return_value=mock_response,
            ),
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_TW = 'gid_tw'
            result = fetch_pnl_tw()

        assert result is None


# ---------------------------------------------------------------------------
# fetch_pnl_us
# ---------------------------------------------------------------------------


class TestFetchPnlUs:
    def test_returns_cached_float_on_cache_hit(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get.return_value = {'value': '890123.0'}

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_US = 'gid_us'
            result = fetch_pnl_us()

        assert result == pytest.approx(890123.0)

    def test_fetches_live_on_cache_miss(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        csv_text = _make_csv_rows()

        mock_response = MagicMock()
        mock_response.text = csv_text
        mock_response.raise_for_status = MagicMock()

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
            patch(
                'fastapistock.repositories.portfolio_repo.httpx.get',
                return_value=mock_response,
            ),
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_US = 'gid_us'
            mock_cfg.PORTFOLIO_CACHE_TTL = 3600
            result = fetch_pnl_us()

        assert result == pytest.approx(890123.0)

    def test_returns_none_on_request_error(self) -> None:
        import httpx as _httpx

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
            patch(
                'fastapistock.repositories.portfolio_repo.httpx.get',
                side_effect=_httpx.RequestError('connection refused'),
            ),
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_US = 'gid_us'
            result = fetch_pnl_us()

        assert result is None

    def test_returns_none_when_config_missing(self) -> None:
        with patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg:
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_US = ''
            result = fetch_pnl_us()

        assert result is None
