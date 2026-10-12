"""Unit tests for portfolio_repo PnL cell-reading functions."""

import csv
import io
import logging
import math
from unittest.mock import MagicMock, patch

import pytest

from fastapistock.repositories.portfolio_repo import (
    _parse_optional_number,
    fetch_pnl_tw,
    fetch_pnl_us,
)
from fastapistock.repositories.twstock_repo import StockNotFoundError

_PRICE_TARGET = 'fastapistock.services.stock_service.get_rich_tw_stock'
_LOGGER_NAME = 'fastapistock.repositories.portfolio_repo'

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


def _filler(symbol: str) -> list[str]:
    return [symbol, 'X', '0', '0', '0', '', '', '', '', '']


def _golden_rows() -> list[list[str]]:
    """Build the 19-row Golden Sample TW sheet (row 0..18) from spec 020."""
    return [
        ['代號', '股名', '持有股數', '買入總金額', '賣出總金額', '平均成本']
        + ['現價', '市值', '未實現損益', '已實現損益'],
        ['0050', 'A', '149957', '8339244', '0', '55.6109', '#N/A', '#N/A']
        + ['#N/A', ''],
        ['0056', 'B', '0', '330026', '333918', '', '58.6', '', '', '3892'],
        ['2330', 'C', '3345', '4646352', '373462', '1389.04', '2550', '8529750']
        + ['4156860', ''],
        _filler('9901'),
        _filler('9902'),
        _filler('9903'),
        ['2317', 'D', '1150', '157671', '0', '137.1', '245', '281750', '124079', ''],
        _filler('9904'),
        _filler('9905'),
        ['5904', 'E', '0', '197600', '198800', '', '#N/A', '', '', '1200'],
        ['006208', 'F', '5000', '651550', '110000', '130.31', '263.25', '1316250']
        + ['774700', ''],
        _filler('9906'),
        ['00687B', 'G', '0', '52180', '55460', '', '#N/A', '', '', '3280'],
        ['009816', 'H', '5000', '54821', '0', '10.96', '16.92', '84600', '29779', ''],
        ['0052', 'I', '2000', '107321', '0', '53.66', '66.95', '133900', '26579', ''],
        ['2454', 'J', '35', '139678', '0', '3990.8', '4630', '162050', '22372', ''],
        ['', '', '', '', '', '', '', 'Unrealize', 'SUM', ''],
        ['', '', '', '', '', '', '', '', '#N/A', '75125'],
    ]


_NUMERIC_I_SUM = 4156860 + 124079 + 774700 + 29779 + 26579 + 22372


def _to_csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


def _mock_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.raise_for_status = MagicMock()
    return response


def _run_tw(
    rows: list[list[str]],
    price_mock: MagicMock,
) -> tuple[float | None, MagicMock]:
    """Run fetch_pnl_tw against *rows* with all IO mocked; return (result, cache)."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    with (
        patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
        patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
        patch(
            'fastapistock.repositories.portfolio_repo.httpx.get',
            return_value=_mock_response(_to_csv(rows)),
        ),
        patch(_PRICE_TARGET, price_mock),
    ):
        mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
        mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_TW = 'gid_tw'
        mock_cfg.PORTFOLIO_CACHE_TTL = 3600
        result = fetch_pnl_tw()
    return result, mock_cache


def _price_returning(price: float) -> MagicMock:
    return MagicMock(return_value=MagicMock(price=price))


def _messages_containing(caplog: pytest.LogCaptureFixture, text: str) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and text in r.getMessage()
    ]


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

    def test_returns_none_when_summary_is_na(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        rows = [['0'] * 10 for _ in range(22)]
        rows[20][7] = '#N/A'

        with (
            patch('fastapistock.repositories.portfolio_repo.redis_cache', mock_cache),
            patch('fastapistock.repositories.portfolio_repo.config') as mock_cfg,
            patch(
                'fastapistock.repositories.portfolio_repo.httpx.get',
                return_value=_mock_response(_to_csv(rows)),
            ),
            patch(_PRICE_TARGET) as mock_price,
        ):
            mock_cfg.GOOGLE_SHEETS_ID = 'sheet_id'
            mock_cfg.GOOGLE_SHEETS_PORTFOLIO_GID_US = 'gid_us'
            result = fetch_pnl_us()

        assert result is None
        mock_price.assert_not_called()
        mock_cache.put.assert_not_called()


# ---------------------------------------------------------------------------
# TW #N/A fallback (spec 020)
# ---------------------------------------------------------------------------


class TestFetchPnlTwFallback:
    def test_fallback_sums_numeric_rows_without_price_lookup(self) -> None:
        rows = _golden_rows()
        rows[1][8] = '100000'
        price = _price_returning(60.0)

        result, mock_cache = _run_tw(rows, price)

        assert result == pytest.approx(_NUMERIC_I_SUM + 100000)
        price.assert_not_called()
        mock_cache.put.assert_not_called()

    def test_fallback_recomputes_na_row_with_live_price(self) -> None:
        price = _price_returning(60.0)

        result, _ = _run_tw(_golden_rows(), price)

        # 2330 uses Sheet I (4156860), not H-(D-E)=4256860; shares==0 rows ignored
        assert result == pytest.approx(5792545.0)
        price.assert_called_once_with('0050')

    def test_fallback_result_not_cached(self) -> None:
        result, mock_cache = _run_tw(_golden_rows(), _price_returning(60.0))

        assert result is not None
        mock_cache.put.assert_not_called()

    def test_fallback_logs_warning_with_na_symbols(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            _run_tw(_golden_rows(), _price_returning(60.0))

        logs = _messages_containing(caplog, 'row-by-row fallback')
        assert len(logs) == 1
        assert '0050' in logs[0]
        assert '#N/A' in logs[0]

    def test_fallback_returns_none_when_price_lookup_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        price = MagicMock(side_effect=StockNotFoundError('0050'))

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result, mock_cache = _run_tw(_golden_rows(), price)

        assert result is None
        mock_cache.put.assert_not_called()
        failed = _messages_containing(caplog, 'fallback failed')
        assert len(failed) == 1
        assert '0050' in failed[0]
        assert _messages_containing(caplog, 'TW live price unavailable for 0050')

    @pytest.mark.parametrize('bad_price', [0.0, -1.0, math.nan, math.inf])
    def test_fallback_returns_none_when_price_non_positive_or_nan(
        self, bad_price: float
    ) -> None:
        result, mock_cache = _run_tw(_golden_rows(), _price_returning(bad_price))

        assert result is None
        mock_cache.put.assert_not_called()

    def test_fallback_recomputes_row_with_non_finite_pnl(self) -> None:
        rows = _golden_rows()
        rows[1][8] = 'nan'  # 0050 column I non-finite -> recompute path
        price = _price_returning(60.0)

        result, _ = _run_tw(rows, price)

        assert result == pytest.approx(5792545.0)
        price.assert_called_once_with('0050')

    def test_fallback_returns_none_when_any_of_multiple_fails(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        rows = _golden_rows()
        rows[3][8] = '#N/A'  # 2330 also needs recompute

        def _lookup(code: str) -> MagicMock:
            if code == '2330':
                raise RuntimeError('boom')
            return MagicMock(price=60.0)

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result, _ = _run_tw(rows, MagicMock(side_effect=_lookup))

        assert result is None
        failed = _messages_containing(caplog, 'fallback failed')
        assert len(failed) == 1
        assert '2330' in failed[0]
        assert '0050' not in failed[0]

    def test_fallback_returns_none_when_buy_total_unparseable(self) -> None:
        rows = _golden_rows()
        rows[1][3] = '#N/A'

        result, _ = _run_tw(rows, _price_returning(60.0))

        assert result is None

    def test_fallback_treats_blank_buy_sell_as_zero(self) -> None:
        rows = _golden_rows()
        rows[1][3] = ''
        rows[1][4] = ''

        result, _ = _run_tw(rows, _price_returning(60.0))

        assert result == pytest.approx(_NUMERIC_I_SUM + 149957 * 60.0)

    def test_fallback_returns_none_when_shares_unparseable(self) -> None:
        rows = _golden_rows()
        rows[3][2] = '#N/A'

        result, _ = _run_tw(rows, _price_returning(60.0))

        assert result is None

    def test_fallback_returns_none_when_no_holdings(self) -> None:
        rows = _golden_rows()
        for row in rows[1:17]:
            row[2] = '0'
        price = _price_returning(60.0)

        result, _ = _run_tw(rows, price)

        assert result is None
        price.assert_not_called()

    def test_fallback_includes_alphanumeric_symbol(self) -> None:
        rows = _golden_rows()
        rows[1][8] = '0'  # 0050 numeric
        rows[13] = ['00687B', 'G', '1000', '30000', '0', '30', '#N/A']  # len < 9
        price = _price_returning(32.0)

        result, _ = _run_tw(rows, price)

        assert result == pytest.approx(_NUMERIC_I_SUM + 1000 * 32.0 - 30000)
        price.assert_called_once_with('00687B')

    def test_valid_summary_does_not_call_price_lookup(self) -> None:
        rows = _golden_rows()
        rows[18][8] = '5,000,000'
        price = _price_returning(60.0)

        result, mock_cache = _run_tw(rows, price)

        assert result == pytest.approx(5000000.0)
        price.assert_not_called()
        mock_cache.put.assert_called_once()


class TestParseOptionalNumber:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('#N/A', None),
            ('', None),
            ('  ', None),
            ('1,234', 1234.0),
            ('-5', -5.0),
            ('nan', None),
            ('inf', None),
            ('-inf', None),
        ],
    )
    def test_parse(self, raw: str, expected: float | None) -> None:
        assert _parse_optional_number(raw) == expected
