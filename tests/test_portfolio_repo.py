"""Tests for portfolio_repo: CSV parsing, error handling, and degradation."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from fastapistock.repositories.portfolio_repo import (
    PortfolioEntry,
    _parse_number,
    fetch_portfolio,
)

_MOD = 'fastapistock.repositories.portfolio_repo.config'
_PATCH_ID = f'{_MOD}.GOOGLE_SHEETS_ID'
_PATCH_GID = f'{_MOD}.GOOGLE_SHEETS_PORTFOLIO_GID'

# ---------------------------------------------------------------------------
# _parse_number unit tests
# ---------------------------------------------------------------------------


def test_parse_number_plain_integer() -> None:
    assert _parse_number('1000') == 1000.0


def test_parse_number_with_thousands_comma() -> None:
    assert _parse_number('1,000') == 1000.0


def test_parse_number_negative_with_comma() -> None:
    assert _parse_number('-75,000') == -75000.0


def test_parse_number_decimal() -> None:
    assert _parse_number('820.00') == 820.0


def test_parse_number_empty_string() -> None:
    assert _parse_number('') == 0.0


def test_parse_number_whitespace_only() -> None:
    assert _parse_number('   ') == 0.0


def test_parse_number_with_surrounding_spaces() -> None:
    assert _parse_number(' 1,234.56 ') == pytest.approx(1234.56)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEADER = 'symbol,name,shares,col_d,col_e,avg_cost,col_g,col_h,unrealized_pnl\n'


def _make_csv(*data_rows: str) -> str:
    return _HEADER + '\n'.join(data_rows)


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# fetch_portfolio tests
# ---------------------------------------------------------------------------


def test_fetch_portfolio_normal_two_rows() -> None:
    csv_text = _make_csv(
        '2330,台積電,1000,,, 820.00,,,75000',
        '2454,聯發科,500,,, 850.00,,,-35000',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        result = fetch_portfolio()

    assert '2330' in result
    assert '2454' in result
    e2330 = result['2330']
    assert e2330.shares == 1000
    assert e2330.avg_cost == pytest.approx(820.0)
    assert e2330.unrealized_pnl == pytest.approx(75000.0)

    e2454 = result['2454']
    assert e2454.shares == 500
    assert e2454.avg_cost == pytest.approx(850.0)
    assert e2454.unrealized_pnl == pytest.approx(-35000.0)


def test_fetch_portfolio_thousands_and_negative() -> None:
    # Google Sheets quotes values that contain commas
    csv_text = _make_csv('2330,台積電,1000,,,"1,000.00",,,"-75,000"')
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        result = fetch_portfolio()

    assert result['2330'].avg_cost == pytest.approx(1000.0)
    assert result['2330'].unrealized_pnl == pytest.approx(-75000.0)


def test_fetch_portfolio_header_row_skipped() -> None:
    """First row must never become a dict entry even if it looks numeric."""
    csv_text = 'symbol,name,shares,d,e,avg_cost,g,h,pnl\n'
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        result = fetch_portfolio()

    assert result == {}


def test_fetch_portfolio_non_numeric_symbol_skipped() -> None:
    csv_text = _make_csv(
        '2330,台積電,1000,,,820.00,,,75000',
        '小計,,,,,,,,',
        ',,,,,,,,',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        result = fetch_portfolio()

    assert list(result.keys()) == ['2330']


def test_fetch_portfolio_request_error_returns_empty() -> None:
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', side_effect=httpx.RequestError('timeout')),
    ):
        result = fetch_portfolio()

    assert result == {}


def test_fetch_portfolio_http_4xx_returns_empty() -> None:
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        '404', request=MagicMock(), response=MagicMock()
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=resp),
    ):
        result = fetch_portfolio()

    assert result == {}


def test_fetch_portfolio_missing_sheet_id_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        patch(_PATCH_ID, ''),
        patch(_PATCH_GID, '456'),
    ):
        result = fetch_portfolio()

    assert result == {}
    assert any('not configured' in r.message for r in caplog.records)


def test_fetch_portfolio_missing_gid_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, ''),
    ):
        result = fetch_portfolio()

    assert result == {}
    assert any('not configured' in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# PortfolioEntry immutability
# ---------------------------------------------------------------------------


def test_portfolio_entry_immutable() -> None:
    entry = PortfolioEntry(
        symbol='2330', shares=1000, avg_cost=820.0, unrealized_pnl=75000.0
    )
    with pytest.raises(AttributeError):
        entry.shares = 999  # type: ignore[misc]
