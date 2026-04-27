"""Repository for spec-006 report history persistence (Postgres + Redis cache).

Provides UPSERT helpers for the per-symbol snapshot and per-period summary
tables, plus read-side helpers for the ``GET /reports/history`` endpoints.

Public dataclasses (:class:`SymbolSnapshot`, :class:`ReportSummary`) are
defined here to avoid circular imports between the repository and the
service layer.

All public functions emit structured log events under the
``fastapistock.report_history`` namespace per spec E-1, e.g.
``report_history.repo.upsert_symbol_snapshots.ok`` /
``report_history.repo.upsert_symbol_snapshots.fail``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from fastapistock.cache import redis_cache
from fastapistock.db.engine import SessionLocal
from fastapistock.db.models import PortfolioReportSummary, PortfolioSymbolSnapshot

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger('fastapistock.report_history')

OPTIONS_CACHE_KEY: str = 'reports:history:options'
OPTIONS_CACHE_TTL: int = 600


@dataclass(frozen=True)
class SymbolSnapshot:
    """Per-symbol snapshot row for one report period.

    Attributes:
        report_type: ``'weekly'`` or ``'monthly'``.
        report_period: ``YYYY-MM-DD`` (weekly) or ``YYYY-MM`` (monthly).
        market: ``'TW'`` or ``'US'``.
        symbol: Stock ticker (TW numeric code or US ticker).
        shares: Position size at snapshot time.
        avg_cost: Weighted-average cost per share.
        current_price: Price used for the snapshot.
        market_value: ``shares * current_price``.
        unrealized_pnl: Currency matches ``market``.
        pnl_pct: Optional percent return; ``None`` when undefined.
        pnl_delta: Difference vs. the previous period; ``None`` for first.
        captured_at: Timezone-aware Asia/Taipei timestamp.
    """

    report_type: str
    report_period: str
    market: str
    symbol: str
    shares: Decimal
    avg_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    pnl_pct: Decimal | None
    pnl_delta: Decimal | None
    captured_at: datetime


@dataclass(frozen=True)
class ReportSummary:
    """Aggregated summary row for one (report_type, report_period) tuple.

    Attributes:
        report_type: ``'weekly'`` or ``'monthly'``.
        report_period: ``YYYY-MM-DD`` (weekly) or ``YYYY-MM`` (monthly).
        pnl_tw_total: Total TW unrealized PnL in TWD.
        pnl_us_total: Total US unrealized PnL in USD.
        pnl_tw_delta: Diff vs. previous TW total; ``None`` for first.
        pnl_us_delta: Diff vs. previous US total; ``None`` for first.
        buy_amount_twd: Period's TWD buy amount; ``None`` if unknown.
        signals_count: Cost-signals fired during the period.
        symbols_count: Distinct symbols held during the period.
        captured_at: Timezone-aware Asia/Taipei timestamp.
    """

    report_type: str
    report_period: str
    pnl_tw_total: Decimal
    pnl_us_total: Decimal
    pnl_tw_delta: Decimal | None
    pnl_us_delta: Decimal | None
    buy_amount_twd: Decimal | None
    signals_count: int
    symbols_count: int
    captured_at: datetime


def _row_to_symbol_snapshot(row: PortfolioSymbolSnapshot) -> SymbolSnapshot:
    """Convert an ORM row to the immutable :class:`SymbolSnapshot` dataclass."""
    return SymbolSnapshot(
        report_type=row.report_type,
        report_period=row.report_period,
        market=row.market,
        symbol=row.symbol,
        shares=row.shares,
        avg_cost=row.avg_cost,
        current_price=row.current_price,
        market_value=row.market_value,
        unrealized_pnl=row.unrealized_pnl,
        pnl_pct=row.pnl_pct,
        pnl_delta=row.pnl_delta,
        captured_at=row.captured_at,
    )


def _row_to_report_summary(row: PortfolioReportSummary) -> ReportSummary:
    """Convert an ORM row to the immutable :class:`ReportSummary` dataclass."""
    return ReportSummary(
        report_type=row.report_type,
        report_period=row.report_period,
        pnl_tw_total=row.pnl_tw_total,
        pnl_us_total=row.pnl_us_total,
        pnl_tw_delta=row.pnl_tw_delta,
        pnl_us_delta=row.pnl_us_delta,
        buy_amount_twd=row.buy_amount_twd,
        signals_count=row.signals_count,
        symbols_count=row.symbols_count,
        captured_at=row.captured_at,
    )


def _symbol_snapshot_payload(row: SymbolSnapshot) -> dict[str, object]:
    """Build the INSERT/UPDATE payload for a :class:`SymbolSnapshot`."""
    return {
        'report_type': row.report_type,
        'report_period': row.report_period,
        'market': row.market,
        'symbol': row.symbol,
        'shares': row.shares,
        'avg_cost': row.avg_cost,
        'current_price': row.current_price,
        'market_value': row.market_value,
        'unrealized_pnl': row.unrealized_pnl,
        'pnl_pct': row.pnl_pct,
        'pnl_delta': row.pnl_delta,
        'captured_at': row.captured_at,
    }


def _report_summary_payload(row: ReportSummary) -> dict[str, object]:
    """Build the INSERT/UPDATE payload for a :class:`ReportSummary`."""
    return {
        'report_type': row.report_type,
        'report_period': row.report_period,
        'pnl_tw_total': row.pnl_tw_total,
        'pnl_us_total': row.pnl_us_total,
        'pnl_tw_delta': row.pnl_tw_delta,
        'pnl_us_delta': row.pnl_us_delta,
        'buy_amount_twd': row.buy_amount_twd,
        'signals_count': row.signals_count,
        'symbols_count': row.symbols_count,
        'captured_at': row.captured_at,
    }


_SYMBOL_CONFLICT_COLS: tuple[str, ...] = (
    'report_type',
    'report_period',
    'market',
    'symbol',
)
_SYMBOL_UPDATE_COLS: tuple[str, ...] = (
    'shares',
    'avg_cost',
    'current_price',
    'market_value',
    'unrealized_pnl',
    'pnl_pct',
    'pnl_delta',
    'captured_at',
)
_SUMMARY_CONFLICT_COLS: tuple[str, ...] = ('report_type', 'report_period')
_SUMMARY_UPDATE_COLS: tuple[str, ...] = (
    'pnl_tw_total',
    'pnl_us_total',
    'pnl_tw_delta',
    'pnl_us_delta',
    'buy_amount_twd',
    'signals_count',
    'symbols_count',
    'captured_at',
)


def _normalize_period_bound(d: date | None, report_type: str) -> str | None:
    """Format a ``date`` bound to match the ``report_period`` column shape.

    Monthly snapshots store ``report_period`` as ``YYYY-MM``; weekly (and any
    future date-based formats) use ``YYYY-MM-DD``. Naively casting a ``date``
    to its ISO form would mis-compare against monthly rows lexicographically
    (e.g. ``'2026-02' < '2026-02-01'``), so this helper drops the day part
    when the report type is monthly.

    Args:
        d: Bound to normalize; ``None`` is passed through unchanged.
        report_type: ``'weekly'`` or ``'monthly'`` (or future formats).

    Returns:
        Normalized string suitable for ``WHERE report_period >= ?`` /
        ``WHERE report_period <= ?``, or ``None`` when ``d`` is ``None``.
    """
    if d is None:
        return None
    if report_type == 'monthly':
        return d.strftime('%Y-%m')
    return d.strftime('%Y-%m-%d')


def _dialect_upsert(
    session: Session,
    table: type[PortfolioSymbolSnapshot] | type[PortfolioReportSummary],
    values: list[dict[str, object]] | dict[str, object],
    *,
    index_elements: tuple[str, ...],
    update_cols: tuple[str, ...],
) -> None:
    """Dialect-aware UPSERT supporting Postgres and SQLite (for tests).

    Args:
        session: Active SQLAlchemy session.
        table: ORM mapped class to insert into.
        values: Single payload dict or list of payload dicts.
        index_elements: Columns forming the unique constraint to detect conflicts.
        update_cols: Columns to overwrite when a conflict is detected.
    """
    dialect_name = session.bind.dialect.name if session.bind is not None else ''
    if dialect_name == 'sqlite':
        sqlite_stmt = sqlite_insert(table).values(values)
        sqlite_excluded = sqlite_stmt.excluded
        sqlite_set = {col: sqlite_excluded[col] for col in update_cols}
        session.execute(
            sqlite_stmt.on_conflict_do_update(
                index_elements=list(index_elements),
                set_=sqlite_set,
            )
        )
        return
    pg_stmt = pg_insert(table).values(values)
    pg_excluded = pg_stmt.excluded
    pg_set = {col: pg_excluded[col] for col in update_cols}
    session.execute(
        pg_stmt.on_conflict_do_update(
            index_elements=list(index_elements),
            set_=pg_set,
        )
    )


def upsert_symbol_snapshots(rows: list[SymbolSnapshot]) -> int:
    """Bulk UPSERT per-symbol snapshot rows.

    Args:
        rows: Snapshot rows to insert or update; empty list is a no-op.

    Returns:
        Number of rows persisted (equal to ``len(rows)`` on success).
    """
    if not rows:
        logger.info('report_history.repo.upsert_symbol_snapshots.skip_empty')
        return 0
    started = time.perf_counter()
    payloads = [_symbol_snapshot_payload(row) for row in rows]
    try:
        with SessionLocal() as session:
            _dialect_upsert(
                session,
                PortfolioSymbolSnapshot,
                payloads,
                index_elements=_SYMBOL_CONFLICT_COLS,
                update_cols=_SYMBOL_UPDATE_COLS,
            )
            session.commit()
    except SQLAlchemyError as exc:
        logger.exception(
            'report_history.repo.upsert_symbol_snapshots.fail',
            extra={
                'rows': len(rows),
                'error_type': type(exc).__name__,
                'error_message': str(exc),
            },
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        'report_history.repo.upsert_symbol_snapshots.ok',
        extra={'rows': len(rows), 'duration_ms': duration_ms},
    )
    invalidate_options_cache()
    return len(rows)


def upsert_report_summary(row: ReportSummary) -> None:
    """Insert or update a single :class:`ReportSummary` row.

    Args:
        row: Summary row to persist; conflict resolved on
            ``(report_type, report_period)``.
    """
    started = time.perf_counter()
    try:
        with SessionLocal() as session:
            _dialect_upsert(
                session,
                PortfolioReportSummary,
                _report_summary_payload(row),
                index_elements=_SUMMARY_CONFLICT_COLS,
                update_cols=_SUMMARY_UPDATE_COLS,
            )
            session.commit()
    except SQLAlchemyError as exc:
        logger.exception(
            'report_history.repo.upsert_report_summary.fail',
            extra={
                'report_type': row.report_type,
                'report_period': row.report_period,
                'error_type': type(exc).__name__,
                'error_message': str(exc),
            },
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        'report_history.repo.upsert_report_summary.ok',
        extra={
            'report_type': row.report_type,
            'report_period': row.report_period,
            'duration_ms': duration_ms,
        },
    )
    invalidate_options_cache()


def list_symbol_history(
    *,
    symbol: str,
    market: str,
    report_type: str = 'monthly',
    since: date | None = None,
    until: date | None = None,
    limit: int = 100,
) -> list[SymbolSnapshot]:
    """Return per-symbol snapshots ordered by ``report_period`` ASC.

    The ``since`` / ``until`` filters are normalized via
    :func:`_normalize_period_bound` so they match the column's storage shape:
    ``YYYY-MM`` for monthly, ``YYYY-MM-DD`` for weekly. This guarantees that
    e.g. ``since=date(2026, 2, 28)`` still matches the ``'2026-02'`` row.

    Args:
        symbol: Stock ticker to filter on.
        market: ``'TW'`` or ``'US'``.
        report_type: ``'weekly'`` or ``'monthly'``.
        since: Inclusive lower bound on ``report_period`` (date).
        until: Inclusive upper bound on ``report_period`` (date).
        limit: Maximum number of rows to return.

    Returns:
        Ordered list of :class:`SymbolSnapshot` (oldest period first).
    """
    since_bound = _normalize_period_bound(since, report_type)
    until_bound = _normalize_period_bound(until, report_type)
    try:
        with SessionLocal() as session:
            stmt = (
                select(PortfolioSymbolSnapshot)
                .where(
                    PortfolioSymbolSnapshot.symbol == symbol,
                    PortfolioSymbolSnapshot.market == market,
                    PortfolioSymbolSnapshot.report_type == report_type,
                )
                .order_by(PortfolioSymbolSnapshot.report_period.desc())
                .limit(limit)
            )
            if since_bound is not None:
                stmt = stmt.where(PortfolioSymbolSnapshot.report_period >= since_bound)
            if until_bound is not None:
                stmt = stmt.where(PortfolioSymbolSnapshot.report_period <= until_bound)
            orm_rows = session.execute(stmt).scalars().all()
    except SQLAlchemyError as exc:
        logger.exception(
            'report_history.repo.list_symbol_history.fail',
            extra={
                'symbol': symbol,
                'market': market,
                'error_type': type(exc).__name__,
            },
        )
        raise
    rows = [_row_to_symbol_snapshot(r) for r in reversed(orm_rows)]
    logger.info(
        'report_history.repo.list_symbol_history.ok',
        extra={
            'symbol': symbol,
            'market': market,
            'report_type': report_type,
            'records': len(rows),
        },
    )
    return rows


def list_summary_history(
    *,
    report_type: str = 'monthly',
    market: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 100,
) -> list[ReportSummary]:
    """Return summary rows ordered by ``report_period`` ASC.

    The ``market`` argument does not change the SQL because there is only one
    summary table; callers (router/service) decide whether to project the
    other market's columns into the response.

    Args:
        report_type: ``'weekly'`` or ``'monthly'``.
        market: Reserved; ignored at SQL level (caller projects columns).
        since: Inclusive lower bound on ``report_period``.
        until: Inclusive upper bound on ``report_period``.
        limit: Maximum number of rows to return.

    Returns:
        Ordered list of :class:`ReportSummary` (oldest period first).
    """
    del market  # interface placeholder; caller projects columns
    since_bound = _normalize_period_bound(since, report_type)
    until_bound = _normalize_period_bound(until, report_type)
    try:
        with SessionLocal() as session:
            stmt = (
                select(PortfolioReportSummary)
                .where(PortfolioReportSummary.report_type == report_type)
                .order_by(PortfolioReportSummary.report_period.desc())
                .limit(limit)
            )
            if since_bound is not None:
                stmt = stmt.where(PortfolioReportSummary.report_period >= since_bound)
            if until_bound is not None:
                stmt = stmt.where(PortfolioReportSummary.report_period <= until_bound)
            orm_rows = session.execute(stmt).scalars().all()
    except SQLAlchemyError as exc:
        logger.exception(
            'report_history.repo.list_summary_history.fail',
            extra={
                'report_type': report_type,
                'error_type': type(exc).__name__,
            },
        )
        raise
    rows = [_row_to_report_summary(r) for r in reversed(orm_rows)]
    logger.info(
        'report_history.repo.list_summary_history.ok',
        extra={'report_type': report_type, 'records': len(rows)},
    )
    return rows


def _build_options_payload() -> dict[str, object]:
    """Run the ``DISTINCT`` queries that back :func:`list_options`.

    Returns:
        Plain dict matching the ``GET /reports/history/options`` response.
    """
    with SessionLocal() as session:
        symbol_rows = session.execute(
            select(
                PortfolioSymbolSnapshot.market,
                PortfolioSymbolSnapshot.symbol,
            )
            .distinct()
            .order_by(
                PortfolioSymbolSnapshot.market.asc(),
                PortfolioSymbolSnapshot.symbol.asc(),
            )
        ).all()

        period_rows = session.execute(
            select(
                PortfolioSymbolSnapshot.report_type,
                PortfolioSymbolSnapshot.report_period,
            )
            .distinct()
            .order_by(
                PortfolioSymbolSnapshot.report_type.asc(),
                PortfolioSymbolSnapshot.report_period.asc(),
            )
        ).all()

        latest = session.execute(
            select(PortfolioSymbolSnapshot.captured_at)
            .order_by(PortfolioSymbolSnapshot.captured_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    symbols: dict[str, list[str]] = {'TW': [], 'US': []}
    for market, symbol in symbol_rows:
        symbols.setdefault(market, []).append(symbol)

    periods: dict[str, list[str]] = {'weekly': [], 'monthly': []}
    for report_type, report_period in period_rows:
        periods.setdefault(report_type, []).append(report_period)

    return {
        'markets': ['TW', 'US'],
        'report_types': ['weekly', 'monthly'],
        'symbols': symbols,
        'periods': periods,
        'latest_captured_at': latest.isoformat() if latest is not None else None,
    }


def _try_cache_get() -> dict[str, object] | None:
    """Attempt to read the options payload from Redis.

    Returns:
        Cached payload, or ``None`` on miss / Redis failure.
    """
    try:
        return redis_cache.get(OPTIONS_CACHE_KEY)
    except Exception as exc:
        logger.warning(
            'report_history.repo.list_options.cache_read_fail',
            extra={'error_type': type(exc).__name__, 'error_message': str(exc)},
        )
        return None


def _try_cache_put(payload: dict[str, object]) -> None:
    """Best-effort write of the options payload to Redis."""
    try:
        redis_cache.put(OPTIONS_CACHE_KEY, payload, OPTIONS_CACHE_TTL)
    except Exception as exc:
        logger.warning(
            'report_history.repo.list_options.cache_write_fail',
            extra={'error_type': type(exc).__name__, 'error_message': str(exc)},
        )


def list_options() -> dict[str, object]:
    """Return metadata used to populate UI selectors (markets / symbols / periods).

    Wraps a Redis cache (``reports:history:options``, TTL 600s). On cache
    miss or Redis failure the call falls back to a direct DB query.

    Returns:
        Dict with keys ``markets``, ``report_types``, ``symbols``,
        ``periods``, and ``latest_captured_at``.
    """
    cached = _try_cache_get()
    if cached is not None:
        logger.info('report_history.repo.list_options.cache_hit')
        return cached
    try:
        payload = _build_options_payload()
    except SQLAlchemyError as exc:
        logger.exception(
            'report_history.repo.list_options.fail',
            extra={'error_type': type(exc).__name__},
        )
        raise
    _try_cache_put(payload)
    symbols_map: dict[str, list[str]] = payload['symbols']  # type: ignore[assignment]
    logger.info(
        'report_history.repo.list_options.ok',
        extra={'symbol_count': sum(len(v) for v in symbols_map.values())},
    )
    return payload


def invalidate_options_cache() -> None:
    """Drop the options Redis cache key.

    Best-effort: Redis errors are swallowed so a transient cache outage never
    blocks an UPSERT pipeline.
    """
    try:
        redis_cache.invalidate(OPTIONS_CACHE_KEY)
        logger.info('report_history.repo.invalidate_options_cache.ok')
    except Exception as exc:
        logger.warning(
            'report_history.repo.invalidate_options_cache.fail',
            extra={'error_type': type(exc).__name__, 'error_message': str(exc)},
        )
