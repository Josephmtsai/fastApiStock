"""Integration tests for ``GET /api/v1/reports/history*`` (spec-006 Phase 4)."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fastapistock.main import app
from fastapistock.repositories import report_history_repo
from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
    upsert_report_summary,
    upsert_symbol_snapshots,
)

client = TestClient(app)

_TZ = ZoneInfo('Asia/Taipei')
_HISTORY_URL = '/api/v1/reports/history'
_OPTIONS_URL = '/api/v1/reports/history/options'


# ── Fixtures ───────────────────────────────────────────────────────────────


def _snapshot(
    *,
    report_period: str,
    market: str = 'TW',
    symbol: str = '2330',
    report_type: str = 'monthly',
    shares: str = '1000',
    avg_cost: str = '750.5',
    current_price: str = '820.0',
    market_value: str = '820000.00',
    unrealized_pnl: str = '69500.00',
    pnl_pct: str | None = '9.2594',
    pnl_delta: str | None = '15000.00',
    captured_at: datetime | None = None,
) -> SymbolSnapshot:
    return SymbolSnapshot(
        report_type=report_type,
        report_period=report_period,
        market=market,
        symbol=symbol,
        shares=Decimal(shares),
        avg_cost=Decimal(avg_cost),
        current_price=Decimal(current_price),
        market_value=Decimal(market_value),
        unrealized_pnl=Decimal(unrealized_pnl),
        pnl_pct=Decimal(pnl_pct) if pnl_pct is not None else None,
        pnl_delta=Decimal(pnl_delta) if pnl_delta is not None else None,
        captured_at=captured_at or datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


def _summary(
    *,
    report_period: str,
    report_type: str = 'monthly',
    pnl_tw_total: str = '500000.00',
    pnl_us_total: str = '8000.00',
    pnl_tw_delta: str | None = '20000.00',
    pnl_us_delta: str | None = '300.00',
    buy_amount_twd: str | None = '100000.00',
    signals_count: int = 3,
    symbols_count: int = 8,
    captured_at: datetime | None = None,
) -> ReportSummary:
    return ReportSummary(
        report_type=report_type,
        report_period=report_period,
        pnl_tw_total=Decimal(pnl_tw_total),
        pnl_us_total=Decimal(pnl_us_total),
        pnl_tw_delta=Decimal(pnl_tw_delta) if pnl_tw_delta is not None else None,
        pnl_us_delta=Decimal(pnl_us_delta) if pnl_us_delta is not None else None,
        buy_amount_twd=Decimal(buy_amount_twd) if buy_amount_twd is not None else None,
        signals_count=signals_count,
        symbols_count=symbols_count,
        captured_at=captured_at or datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    """Populate the in-memory DB with a small TW + US fixture."""
    upsert_symbol_snapshots(
        [
            _snapshot(report_period='2026-02', symbol='2330'),
            _snapshot(report_period='2026-03', symbol='2330'),
            _snapshot(report_period='2026-04', symbol='2330'),
            _snapshot(
                report_period='2026-04',
                market='US',
                symbol='AAPL',
                shares='10',
                avg_cost='150.0',
                current_price='180.0',
                market_value='1800.00',
                unrealized_pnl='300.00',
                pnl_pct='20.0',
                pnl_delta='50.00',
            ),
        ]
    )
    for period in ('2026-02', '2026-03', '2026-04'):
        upsert_report_summary(_summary(report_period=period))
    # Drop the cache populated during seeding so each test sees fresh data.
    report_history_repo.invalidate_options_cache()
    return db_session


# ── Mode A: per-symbol ────────────────────────────────────────────────────


class TestSymbolMode:
    """``?symbol=…&market=…`` returns mode=symbol time series."""

    def test_returns_symbol_time_series(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'symbol': '2330', 'market': 'TW'})
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'success'
        data = body['data']
        assert data['mode'] == 'symbol'
        assert data['symbol'] == '2330'
        assert data['market'] == 'TW'
        assert data['report_type'] == 'monthly'
        assert isinstance(data['records'], list)
        assert len(data['records']) == 3
        first = data['records'][0]
        assert first['report_period'] == '2026-02'
        # Decimal → float check
        assert isinstance(first['shares'], float)
        assert isinstance(first['avg_cost'], float)
        assert first['current_price'] == 820.0
        assert isinstance(first['captured_at'], str)
        # ISO 8601 with timezone offset
        assert '+' in first['captured_at'] or first['captured_at'].endswith('Z')

    def test_unknown_symbol_returns_empty_records(self, seeded_db: Session) -> None:
        resp = client.get(
            _HISTORY_URL,
            params={'symbol': 'NOPE', 'market': 'TW'},
        )
        assert resp.status_code == 200
        assert resp.json()['data']['records'] == []


# ── Mode B: dual market summary ───────────────────────────────────────────


class TestSummaryDualMode:
    """No ``symbol``/``market`` → mode=summary with both PnL columns."""

    def test_returns_dual_market_summary(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['mode'] == 'summary'
        assert data['markets'] == ['TW', 'US']
        assert data['report_type'] == 'monthly'
        assert len(data['records']) == 3
        first = data['records'][0]
        assert 'pnl_tw_total' in first
        assert 'pnl_us_total' in first
        assert 'pnl_tw_delta' in first
        assert 'pnl_us_delta' in first
        assert 'pnl_total' not in first  # collapsed shape only on single-market
        assert isinstance(first['pnl_tw_total'], float)


# ── Mode C: single market summary ─────────────────────────────────────────


class TestSummarySingleMarketMode:
    """``?market=TW`` → mode=summary with collapsed pnl_total / pnl_delta."""

    def test_tw_only_collapses_columns(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'market': 'TW'})
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['mode'] == 'summary'
        assert data['markets'] == ['TW']
        first = data['records'][0]
        assert 'pnl_total' in first
        assert 'pnl_delta' in first
        # Opposite-market columns must be absent
        assert 'pnl_tw_total' not in first
        assert 'pnl_us_total' not in first
        assert 'pnl_tw_delta' not in first
        assert 'pnl_us_delta' not in first
        # Value comes from pnl_tw_total
        assert first['pnl_total'] == 500000.0

    def test_us_only_uses_us_columns(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'market': 'US'})
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['markets'] == ['US']
        first = data['records'][0]
        assert first['pnl_total'] == 8000.0
        # delta value comes from pnl_us_delta, not pnl_tw_delta
        assert first['pnl_delta'] == 300.0


# ── Validation ────────────────────────────────────────────────────────────


class TestValidation:
    """Spec C-1 validation rules."""

    def test_symbol_without_market_returns_400(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'symbol': '2330'})
        assert resp.status_code == 400
        assert 'market is required' in resp.json()['detail']

    def test_since_after_until_returns_400(self, seeded_db: Session) -> None:
        resp = client.get(
            _HISTORY_URL,
            params={'since': '2026-04-01', 'until': '2026-01-01'},
        )
        assert resp.status_code == 400
        assert 'since must be <= until' in resp.json()['detail']

    def test_limit_above_max_returns_422(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'limit': 2000})
        assert resp.status_code == 422

    def test_limit_below_one_returns_422(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'limit': 0})
        assert resp.status_code == 422

    def test_invalid_report_type_returns_422(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'report_type': 'daily'})
        assert resp.status_code == 422

    def test_invalid_market_returns_422(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'market': 'JP'})
        assert resp.status_code == 422


# ── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Empty DB / window / serialization."""

    def test_empty_db_returns_empty_records(self, db_session: Session) -> None:
        resp = client.get(_HISTORY_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'success'
        assert body['data']['records'] == []

    def test_since_until_filter_narrows_results(self, seeded_db: Session) -> None:
        resp = client.get(
            _HISTORY_URL,
            params={
                'symbol': '2330',
                'market': 'TW',
                'since': '2026-03-01',
                'until': '2026-03-31',
            },
        )
        assert resp.status_code == 200
        records = resp.json()['data']['records']
        assert len(records) == 1
        assert records[0]['report_period'] == '2026-03'

    def test_limit_truncates_results(self, seeded_db: Session) -> None:
        resp = client.get(
            _HISTORY_URL,
            params={'symbol': '2330', 'market': 'TW', 'limit': 1},
        )
        assert resp.status_code == 200
        assert len(resp.json()['data']['records']) == 1

    def test_response_contains_no_decimal_string(self, seeded_db: Session) -> None:
        resp = client.get(_HISTORY_URL, params={'symbol': '2330', 'market': 'TW'})
        assert resp.status_code == 200
        # Re-serialise to text and grep for 'Decimal(' just in case the test
        # client's automatic JSON parsing hides it. The endpoint returns
        # numbers, never tagged Decimal strings.
        raw = resp.text
        assert 'Decimal(' not in raw
        # All numeric fields are floats (json round-trip preserves type tag).
        first = resp.json()['data']['records'][0]
        for key in ('shares', 'avg_cost', 'current_price', 'market_value'):
            assert isinstance(first[key], float), (
                f'expected float for {key}, got {type(first[key])}'
            )


# ── Options endpoint ──────────────────────────────────────────────────────


class TestOptionsEndpoint:
    """``GET /api/v1/reports/history/options`` returns the cached payload."""

    def test_returns_repo_options(self, seeded_db: Session) -> None:
        resp = client.get(_OPTIONS_URL)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['markets'] == ['TW', 'US']
        assert sorted(data['report_types']) == ['monthly', 'weekly']
        assert '2330' in data['symbols']['TW']
        assert 'AAPL' in data['symbols']['US']
        assert '2026-04' in data['periods']['monthly']
        assert isinstance(data['latest_captured_at'], str)

    def test_empty_db_returns_empty_lists(self, db_session: Session) -> None:
        resp = client.get(_OPTIONS_URL)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['symbols']['TW'] == []
        assert data['symbols']['US'] == []
        assert data['periods']['monthly'] == []
        assert data['periods']['weekly'] == []
        assert data['latest_captured_at'] is None


# ── Defensive: window default ─────────────────────────────────────────────


class TestDefaultWindow:
    """Default since/until applies a 1-year lookback ending today."""

    def test_default_window_is_one_year(self, seeded_db: Session) -> None:
        # We don't assert exact bounds (depends on call time); only that the
        # default behaviour returns rows without 400.
        resp = client.get(_HISTORY_URL, params={'symbol': '2330', 'market': 'TW'})
        assert resp.status_code == 200
        # All 2026-02..04 fall within one year of `today`.
        assert len(resp.json()['data']['records']) == 3


# ── Smoke: serialization isolation ────────────────────────────────────────


def test_isoformat_carries_timezone_offset(seeded_db: Session) -> None:
    """``captured_at`` must include a UTC offset (Asia/Taipei = +08:00)."""
    resp = client.get(_HISTORY_URL, params={'symbol': '2330', 'market': 'TW'})
    captured = resp.json()['data']['records'][0]['captured_at']
    assert captured.endswith('+08:00') or '+08' in captured


# ── Smoke: ensure repo errors propagate via 500 envelope ──────────────────


def test_repo_failure_returns_500_envelope(db_session: Session) -> None:
    """``SQLAlchemyError`` → registered exception handler returns ``error``."""
    with patch.object(
        report_history_repo,
        'list_summary_history',
        side_effect=RuntimeError('boom'),
    ):
        local_client = TestClient(app, raise_server_exceptions=False)
        resp = local_client.get(_HISTORY_URL)
    assert resp.status_code == 500
    body = resp.json()
    assert body['status'] == 'error'


# Helpful when adding new fields — verifies the test file stays in sync with
# the ResponseEnvelope schema.
def test_records_contain_expected_keys(seeded_db: Session) -> None:
    resp = client.get(_HISTORY_URL, params={'symbol': '2330', 'market': 'TW'})
    record: dict[str, Any] = resp.json()['data']['records'][0]
    expected = {
        'report_period',
        'shares',
        'avg_cost',
        'current_price',
        'market_value',
        'unrealized_pnl',
        'pnl_pct',
        'pnl_delta',
        'captured_at',
    }
    assert expected.issubset(record.keys())


# Unused but imported earlier — silence linters.
_ = (json, date)
