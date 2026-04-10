"""Unit tests for investment_plan_repo: CSV parsing, caching, and error handling."""

from datetime import date
from unittest.mock import MagicMock, patch

import httpx
import pytest

from fastapistock.repositories.investment_plan_repo import (
    _parse_date,
    fetch_investment_plan,
)

_MOD_CFG = 'fastapistock.repositories.investment_plan_repo.config'
_MOD_CACHE = 'fastapistock.repositories.investment_plan_repo.redis_cache'
_MOCK_HTTP = 'fastapistock.repositories.investment_plan_repo.httpx.get'


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


def test_parse_date_dash_format() -> None:
    assert _parse_date('2026-04-01') == date(2026, 4, 1)


def test_parse_date_slash_format() -> None:
    assert _parse_date('2026/04/01') == date(2026, 4, 1)


def test_parse_date_invalid_returns_none() -> None:
    assert _parse_date('not-a-date') is None


def test_parse_date_empty_returns_none() -> None:
    assert _parse_date('') is None


# ---------------------------------------------------------------------------
# fetch_investment_plan — config missing
# ---------------------------------------------------------------------------


def test_fetch_returns_empty_when_sheet_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', '')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', '1234')
    result = fetch_investment_plan(date(2026, 4, 10))
    assert result == []


def test_fetch_returns_empty_when_gid_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', 'sheet_id')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', '')
    result = fetch_investment_plan(date(2026, 4, 10))
    assert result == []


# ---------------------------------------------------------------------------
# fetch_investment_plan — cache hit
# ---------------------------------------------------------------------------

_CSV_VALID = (
    'Symbol,Start,End,D,E,Expected,Invested\n'
    'AAPL,2026-04-01,2026-06-30,,,1000,500\n'
    'TSLA,2026-04-01,2026-06-30,,,500,250\n'
)

_CACHED_DATA = [
    {
        'symbol': 'AAPL',
        'start_date': '2026-04-01',
        'end_date': '2026-06-30',
        'expected_usd': 1000.0,
        'invested_usd': 500.0,
    }
]


def test_fetch_uses_cache_on_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', 'sid')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', 'gid')

    cache_get = MagicMock(return_value={'entries': _CACHED_DATA})
    monkeypatch.setattr(_MOD_CACHE + '.get', cache_get)

    result = fetch_investment_plan(date(2026, 4, 10))
    cache_get.assert_called_once()
    assert len(result) == 1
    assert result[0].symbol == 'AAPL'


# ---------------------------------------------------------------------------
# fetch_investment_plan — cache miss → live fetch
# ---------------------------------------------------------------------------


def test_fetch_parses_valid_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', 'sid')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', 'gid')
    monkeypatch.setattr(_MOD_CACHE + '.get', MagicMock(return_value=None))
    monkeypatch.setattr(_MOD_CACHE + '.put', MagicMock())

    mock_resp = MagicMock()
    mock_resp.text = _CSV_VALID
    mock_resp.raise_for_status = MagicMock()

    with patch(_MOCK_HTTP, return_value=mock_resp):
        result = fetch_investment_plan(date(2026, 4, 10))

    assert len(result) == 2
    assert result[0].symbol == 'AAPL'
    assert result[0].expected_usd == pytest.approx(1000.0)
    assert result[0].invested_usd == pytest.approx(500.0)
    assert result[0].start_date == date(2026, 4, 1)
    assert result[0].end_date == date(2026, 6, 30)


def test_fetch_skips_row_with_bad_date(monkeypatch: pytest.MonkeyPatch) -> None:
    csv = (
        'Symbol,Start,End,D,E,Expected,Invested\n'
        'AAPL,bad-date,2026-06-30,,,1000,500\n'
        'TSLA,2026-04-01,2026-06-30,,,500,250\n'
    )
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', 'sid')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', 'gid')
    monkeypatch.setattr(_MOD_CACHE + '.get', MagicMock(return_value=None))
    monkeypatch.setattr(_MOD_CACHE + '.put', MagicMock())

    mock_resp = MagicMock()
    mock_resp.text = csv
    mock_resp.raise_for_status = MagicMock()

    with patch(_MOCK_HTTP, return_value=mock_resp):
        result = fetch_investment_plan(date(2026, 4, 10))

    assert len(result) == 1
    assert result[0].symbol == 'TSLA'


def test_fetch_skips_row_with_blank_amounts(monkeypatch: pytest.MonkeyPatch) -> None:
    csv = (
        'Symbol,Start,End,D,E,Expected,Invested\n'
        'AAPL,2026-04-01,2026-06-30,,,,\n'
        'TSLA,2026-04-01,2026-06-30,,,500,250\n'
    )
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', 'sid')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', 'gid')
    monkeypatch.setattr(_MOD_CACHE + '.get', MagicMock(return_value=None))
    monkeypatch.setattr(_MOD_CACHE + '.put', MagicMock())

    mock_resp = MagicMock()
    mock_resp.text = csv
    mock_resp.raise_for_status = MagicMock()

    with patch(_MOCK_HTTP, return_value=mock_resp):
        result = fetch_investment_plan(date(2026, 4, 10))

    # Row with both F and G = 0 is skipped
    assert len(result) == 1
    assert result[0].symbol == 'TSLA'


def test_fetch_handles_http_error_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', 'sid')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', 'gid')
    monkeypatch.setattr(_MOD_CACHE + '.get', MagicMock(return_value=None))

    with patch(_MOCK_HTTP, side_effect=httpx.RequestError('timeout')):
        result = fetch_investment_plan(date(2026, 4, 10))

    assert result == []


def test_fetch_fallback_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis error during get should fall through to live fetch."""
    import redis

    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_ID', 'sid')
    monkeypatch.setattr(_MOD_CFG + '.GOOGLE_SHEETS_INVESTMENT_PLAN_GID', 'gid')
    monkeypatch.setattr(
        _MOD_CACHE + '.get', MagicMock(side_effect=redis.RedisError('down'))
    )
    monkeypatch.setattr(_MOD_CACHE + '.put', MagicMock())

    mock_resp = MagicMock()
    mock_resp.text = _CSV_VALID
    mock_resp.raise_for_status = MagicMock()

    with patch(_MOCK_HTTP, return_value=mock_resp):
        result = fetch_investment_plan(date(2026, 4, 10))

    assert len(result) == 2
