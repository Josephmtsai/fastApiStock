"""Unit tests for fastapistock.repositories.report_history_repo (spec-006)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from fastapistock.repositories import report_history_repo
from fastapistock.repositories.report_history_repo import (
    OPTIONS_CACHE_KEY,
    ReportSummary,
    SymbolSnapshot,
    invalidate_options_cache,
    list_options,
    list_summary_history,
    list_symbol_history,
    upsert_report_summary,
    upsert_symbol_snapshots,
)

_TZ = ZoneInfo('Asia/Taipei')


def _snapshot(
    *,
    report_type: str = 'monthly',
    report_period: str = '2026-04',
    market: str = 'TW',
    symbol: str = '2330',
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
    report_type: str = 'monthly',
    report_period: str = '2026-04',
    pnl_tw_total: str = '523456.00',
    pnl_us_total: str = '8345.00',
    pnl_tw_delta: str | None = '23456.00',
    pnl_us_delta: str | None = '345.00',
    buy_amount_twd: str | None = '100000.00',
    signals_count: int = 4,
    symbols_count: int = 12,
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


# ---------------------------------------------------------------------------
# upsert_symbol_snapshots
# ---------------------------------------------------------------------------


def test_upsert_symbol_snapshots_inserts_rows(db_session: Session) -> None:
    rows = [_snapshot(symbol='2330'), _snapshot(symbol='0050')]
    written = upsert_symbol_snapshots(rows)
    assert written == 2

    result = list_symbol_history(symbol='2330', market='TW')
    assert len(result) == 1
    assert result[0].symbol == '2330'
    assert result[0].current_price == Decimal('820.0000')


def test_upsert_symbol_snapshots_updates_on_conflict(db_session: Session) -> None:
    upsert_symbol_snapshots([_snapshot(current_price='820.0')])
    upsert_symbol_snapshots([_snapshot(current_price='999.5', pnl_delta='42.00')])

    rows = list_symbol_history(symbol='2330', market='TW')
    assert len(rows) == 1, 'UPSERT must update, not insert duplicate'
    assert rows[0].current_price == Decimal('999.5000')
    assert rows[0].pnl_delta == Decimal('42.00')


def test_upsert_symbol_snapshots_empty_list_returns_zero(db_session: Session) -> None:
    assert upsert_symbol_snapshots([]) == 0
    # No DB call should have happened — DB should still be empty.
    assert list_symbol_history(symbol='2330', market='TW') == []


def test_upsert_symbol_snapshots_invalidates_options_cache(
    db_session: Session,
) -> None:
    # Prime the cache with a stale value.
    from fastapistock.cache import redis_cache

    redis_cache.put(OPTIONS_CACHE_KEY, {'stale': True}, 600)
    assert redis_cache.get(OPTIONS_CACHE_KEY) == {'stale': True}

    upsert_symbol_snapshots([_snapshot()])

    assert redis_cache.get(OPTIONS_CACHE_KEY) is None


# ---------------------------------------------------------------------------
# upsert_report_summary
# ---------------------------------------------------------------------------


def test_upsert_report_summary_insert_then_update(db_session: Session) -> None:
    upsert_report_summary(_summary(pnl_tw_total='100.00'))
    upsert_report_summary(_summary(pnl_tw_total='250.00'))

    rows = list_summary_history(report_type='monthly')
    assert len(rows) == 1
    assert rows[0].pnl_tw_total == Decimal('250.00')


# ---------------------------------------------------------------------------
# list_symbol_history
# ---------------------------------------------------------------------------


def test_list_symbol_history_filters_by_since_until(db_session: Session) -> None:
    # Use weekly (YYYY-MM-DD) periods so since/until lexicographic comparison
    # matches calendar comparison exactly.
    upsert_symbol_snapshots(
        [
            _snapshot(report_type='weekly', report_period='2026-04-05'),
            _snapshot(report_type='weekly', report_period='2026-04-12'),
            _snapshot(report_type='weekly', report_period='2026-04-19'),
            _snapshot(report_type='weekly', report_period='2026-04-26'),
        ]
    )

    rows = list_symbol_history(
        symbol='2330',
        market='TW',
        report_type='weekly',
        since=date(2026, 4, 12),
        until=date(2026, 4, 19),
    )
    periods = [r.report_period for r in rows]
    assert periods == ['2026-04-12', '2026-04-19']


def test_list_symbol_history_monthly_since_includes_same_month(
    db_session: Session,
) -> None:
    """``since=date(2026, 2, 1)`` must include the ``'2026-02'`` monthly row.

    Regression: previously ``since.isoformat()`` produced ``'2026-02-01'``
    which lex-compared GREATER than ``'2026-02'`` and erroneously excluded
    that month. The repo now normalizes monthly bounds to ``YYYY-MM``.
    """
    upsert_symbol_snapshots(
        [
            _snapshot(report_period='2026-01'),
            _snapshot(report_period='2026-02'),
            _snapshot(report_period='2026-03'),
        ]
    )

    rows = list_symbol_history(
        symbol='2330',
        market='TW',
        report_type='monthly',
        since=date(2026, 2, 1),
    )
    assert [r.report_period for r in rows] == ['2026-02', '2026-03']


def test_list_symbol_history_monthly_since_mid_month_includes_month(
    db_session: Session,
) -> None:
    """Any day inside February (e.g. the 28th) must still cover ``'2026-02'``."""
    upsert_symbol_snapshots(
        [
            _snapshot(report_period='2026-01'),
            _snapshot(report_period='2026-02'),
            _snapshot(report_period='2026-03'),
        ]
    )

    rows = list_symbol_history(
        symbol='2330',
        market='TW',
        report_type='monthly',
        since=date(2026, 2, 28),
    )
    assert [r.report_period for r in rows] == ['2026-02', '2026-03']


def test_list_symbol_history_monthly_until_includes_same_month(
    db_session: Session,
) -> None:
    """``until=date(2026, 2, 1)`` must include the ``'2026-02'`` monthly row."""
    upsert_symbol_snapshots(
        [
            _snapshot(report_period='2026-01'),
            _snapshot(report_period='2026-02'),
            _snapshot(report_period='2026-03'),
        ]
    )

    rows = list_symbol_history(
        symbol='2330',
        market='TW',
        report_type='monthly',
        until=date(2026, 2, 1),
    )
    assert [r.report_period for r in rows] == ['2026-01', '2026-02']


def test_list_symbol_history_monthly_cross_month_range(db_session: Session) -> None:
    """Combined since/until across multiple months must include all bounds."""
    upsert_symbol_snapshots(
        [
            _snapshot(report_period='2026-01'),
            _snapshot(report_period='2026-02'),
            _snapshot(report_period='2026-03'),
            _snapshot(report_period='2026-04'),
        ]
    )

    rows = list_symbol_history(
        symbol='2330',
        market='TW',
        report_type='monthly',
        since=date(2026, 2, 15),
        until=date(2026, 3, 10),
    )
    assert [r.report_period for r in rows] == ['2026-02', '2026-03']


def test_list_symbol_history_orders_by_period_asc(db_session: Session) -> None:
    upsert_symbol_snapshots(
        [
            _snapshot(report_period='2026-04'),
            _snapshot(report_period='2026-01'),
            _snapshot(report_period='2026-03'),
        ]
    )
    rows = list_symbol_history(symbol='2330', market='TW')
    assert [r.report_period for r in rows] == ['2026-01', '2026-03', '2026-04']


def test_list_symbol_history_respects_limit(db_session: Session) -> None:
    upsert_symbol_snapshots(
        [_snapshot(report_period=f'2026-0{i}') for i in range(1, 6)]
    )
    rows = list_symbol_history(symbol='2330', market='TW', limit=2)
    assert len(rows) == 2


def test_list_symbol_history_unknown_symbol_returns_empty(db_session: Session) -> None:
    upsert_symbol_snapshots([_snapshot(symbol='2330')])
    assert list_symbol_history(symbol='9999', market='TW') == []


# ---------------------------------------------------------------------------
# list_summary_history
# ---------------------------------------------------------------------------


def test_list_summary_history_filters_by_since_until(db_session: Session) -> None:
    upsert_report_summary(_summary(report_type='weekly', report_period='2026-04-05'))
    upsert_report_summary(_summary(report_type='weekly', report_period='2026-04-12'))
    upsert_report_summary(_summary(report_type='weekly', report_period='2026-04-19'))

    rows = list_summary_history(
        report_type='weekly',
        since=date(2026, 4, 12),
        until=date(2026, 4, 19),
    )
    assert [r.report_period for r in rows] == ['2026-04-12', '2026-04-19']


def test_list_summary_history_monthly_since_includes_same_month(
    db_session: Session,
) -> None:
    """Summary path also normalizes monthly bounds (parallel to symbol path)."""
    upsert_report_summary(_summary(report_period='2026-01'))
    upsert_report_summary(_summary(report_period='2026-02'))
    upsert_report_summary(_summary(report_period='2026-03'))

    rows = list_summary_history(
        report_type='monthly',
        since=date(2026, 2, 1),
        until=date(2026, 2, 28),
    )
    assert [r.report_period for r in rows] == ['2026-02']


def test_list_summary_history_market_arg_ignored_at_sql_level(
    db_session: Session,
) -> None:
    upsert_report_summary(_summary())
    rows_tw = list_summary_history(report_type='monthly', market='TW')
    rows_us = list_summary_history(report_type='monthly', market='US')
    rows_none = list_summary_history(report_type='monthly')
    assert len(rows_tw) == len(rows_us) == len(rows_none) == 1


# ---------------------------------------------------------------------------
# list_options + cache
# ---------------------------------------------------------------------------


def test_list_options_returns_distinct_values(db_session: Session) -> None:
    upsert_symbol_snapshots(
        [
            _snapshot(market='TW', symbol='2330', report_period='2026-03'),
            _snapshot(market='TW', symbol='2330', report_period='2026-04'),
            _snapshot(market='TW', symbol='0050', report_period='2026-04'),
            _snapshot(
                market='US',
                symbol='AAPL',
                report_period='2026-04',
                report_type='monthly',
            ),
            _snapshot(
                market='US',
                symbol='AAPL',
                report_period='2026-04-19',
                report_type='weekly',
            ),
        ]
    )

    options = list_options()

    assert options['markets'] == ['TW', 'US']
    assert options['report_types'] == ['weekly', 'monthly']
    assert options['symbols'] == {
        'TW': ['0050', '2330'],
        'US': ['AAPL'],
    }
    assert options['periods'] == {
        'monthly': ['2026-03', '2026-04'],
        'weekly': ['2026-04-19'],
    }
    assert options['latest_captured_at'] is not None


def test_list_options_cache_hit_skips_db(db_session: Session) -> None:
    from fastapistock.cache import redis_cache

    fake_payload: dict[str, object] = {
        'markets': ['TW', 'US'],
        'report_types': ['weekly', 'monthly'],
        'symbols': {'TW': ['CACHED'], 'US': []},
        'periods': {'weekly': [], 'monthly': []},
        'latest_captured_at': None,
    }
    redis_cache.put(OPTIONS_CACHE_KEY, fake_payload, 600)

    result = list_options()

    assert result['symbols'] == {'TW': ['CACHED'], 'US': []}


def test_list_options_writes_to_cache_on_miss(db_session: Session) -> None:
    from fastapistock.cache import redis_cache

    upsert_symbol_snapshots([_snapshot(symbol='2330', report_period='2026-04')])
    redis_cache.invalidate(OPTIONS_CACHE_KEY)

    list_options()

    cached = redis_cache.get(OPTIONS_CACHE_KEY)
    assert cached is not None
    assert cached['symbols']['TW'] == ['2330']  # type: ignore[index]


def test_list_options_redis_failure_falls_back_to_db(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    upsert_symbol_snapshots([_snapshot(symbol='2330', report_period='2026-04')])

    def _boom(_key: str) -> dict[str, object] | None:
        raise RuntimeError('redis is down')

    def _boom_put(_key: str, _value: dict[str, object], _ttl: int) -> None:
        raise RuntimeError('redis is down')

    monkeypatch.setattr(report_history_repo.redis_cache, 'get', _boom)
    monkeypatch.setattr(report_history_repo.redis_cache, 'put', _boom_put)

    result = list_options()
    assert result['symbols']['TW'] == ['2330']  # type: ignore[index]


def test_invalidate_options_cache_swallows_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_key: str) -> None:
        raise RuntimeError('redis is gone')

    monkeypatch.setattr(report_history_repo.redis_cache, 'invalidate', _boom)
    # Must not raise.
    invalidate_options_cache()
