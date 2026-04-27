"""Router for portfolio weekly/monthly report preview and dispatch endpoints.

All routes live under /api/v1/reports.  Rate limiting is applied globally by
the middleware layer in main.py via the ``/api/v1/reports`` prefix mapping,
not per-route.

Endpoints:
    GET  /api/v1/reports/weekly/preview      — render weekly text only
    GET  /api/v1/reports/monthly/preview     — render monthly text only
    POST /api/v1/reports/weekly/send         — render and dispatch to Telegram
    POST /api/v1/reports/monthly/send        — render and dispatch to Telegram
    POST /api/v1/reports/history/trigger     — manual report-history pipeline run
    GET  /api/v1/reports/history             — query persisted history (spec-006 C-1)
    GET  /api/v1/reports/history/options     — UI selector metadata (spec-006 C-2)
"""

import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from fastapistock import config
from fastapistock.repositories import report_history_repo
from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
)
from fastapistock.schemas.common import ResponseEnvelope
from fastapistock.services.report_service import (
    build_monthly_report,
    build_weekly_report,
    run_report_pipeline,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/reports', tags=['reports'])

_TZ = ZoneInfo('Asia/Taipei')

# spec-006 E-2 — accept YYYY-MM (monthly) or YYYY-MM-DD (weekly Sunday label).
_PERIOD_PATTERN = r'^\d{4}-\d{2}(-\d{2})?$'


# ── Pydantic models ────────────────────────────────────────────────────────


class TriggerHistoryRequest(BaseModel):
    """Body schema for ``POST /api/v1/reports/history/trigger``."""

    report_type: Literal['weekly', 'monthly']
    report_period: str | None = Field(default=None, pattern=_PERIOD_PATTERN)
    dry_run: bool = False
    skip_telegram: bool = True
    skip_sheet: bool = False


# ── Authorization dependency ───────────────────────────────────────────────


def verify_admin_token(authorization: str = Header(default='')) -> None:
    """Validate the Bearer token against ``config.ADMIN_TOKEN``.

    Raises:
        HTTPException: 503 when ``ADMIN_TOKEN`` is unset (endpoint disabled);
            401 when the header is missing, malformed, or the token is wrong.
    """
    if not config.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail='admin trigger not configured')
    if not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='missing bearer token')
    token = authorization.removeprefix('Bearer ').strip()
    if token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail='invalid token')


# ── Preview endpoints ──────────────────────────────────────────────────────


@router.get(
    '/weekly/preview',
    response_model=ResponseEnvelope[dict[str, str]],
    summary='Render the weekly report without dispatching to Telegram',
)
async def preview_weekly() -> ResponseEnvelope[dict[str, str]]:
    """Build the weekly report text and return it in the response envelope.

    Returns:
        ResponseEnvelope carrying ``{'text': <MarkdownV2 body>}`` on success.
    """
    logger.info('Weekly report preview requested')
    text, _ = build_weekly_report(datetime.now(_TZ))
    return ResponseEnvelope(status='success', data={'text': text})


@router.get(
    '/monthly/preview',
    response_model=ResponseEnvelope[dict[str, str]],
    summary='Render the monthly report without dispatching to Telegram',
)
async def preview_monthly() -> ResponseEnvelope[dict[str, str]]:
    """Build the monthly report text and return it in the response envelope.

    Returns:
        ResponseEnvelope carrying ``{'text': <MarkdownV2 body>}`` on success.
    """
    logger.info('Monthly report preview requested')
    text, _ = build_monthly_report(datetime.now(_TZ))
    return ResponseEnvelope(status='success', data={'text': text})


# ── Dispatch endpoints ─────────────────────────────────────────────────────


@router.post(
    '/weekly/send',
    response_model=ResponseEnvelope[None],
    summary='Dispatch the weekly report to the configured Telegram chat',
)
async def trigger_weekly_send() -> ResponseEnvelope[None]:
    """Render and send the weekly report to Telegram.

    Delegates to :func:`run_report_pipeline` (``trigger='manual'``) which
    never raises; underlying errors surface only via the structured log
    stream. The endpoint always returns success once the dispatch attempt
    is scheduled.
    """
    logger.info('Weekly report dispatch requested')
    run_report_pipeline(report_type='weekly', trigger='manual')
    return ResponseEnvelope(status='success', message='weekly report dispatched')


@router.post(
    '/monthly/send',
    response_model=ResponseEnvelope[None],
    summary='Dispatch the monthly report to the configured Telegram chat',
)
async def trigger_monthly_send() -> ResponseEnvelope[None]:
    """Render and send the monthly report to Telegram.

    Delegates to :func:`run_report_pipeline` (``trigger='manual'``) which
    never raises; underlying errors surface only via the structured log
    stream. The endpoint always returns success once the dispatch attempt
    is scheduled.
    """
    logger.info('Monthly report dispatch requested')
    run_report_pipeline(report_type='monthly', trigger='manual')
    return ResponseEnvelope(status='success', message='monthly report dispatched')


# ── Manual history trigger (spec-006 E-2) ──────────────────────────────────


@router.post(
    '/history/trigger',
    response_model=ResponseEnvelope[dict[str, Any]],
    dependencies=[Depends(verify_admin_token)],
    summary='Manually run the report-history pipeline (admin only)',
)
async def trigger_history_run(
    body: TriggerHistoryRequest,
) -> ResponseEnvelope[dict[str, Any]]:
    """Invoke ``run_report_pipeline`` with caller-supplied flags.

    The endpoint is intended for ops use: post-deploy verification, ad-hoc
    re-runs after a scheduler failure, and one-off baseline creation. The
    underlying pipeline never raises, so callers always see a 200 response
    with the structured ``RunReportResult`` payload describing each step.
    """
    logger.info(
        'history trigger requested: type=%s period=%s dry_run=%s',
        body.report_type,
        body.report_period,
        body.dry_run,
    )
    result = run_report_pipeline(
        report_type=body.report_type,
        report_period=body.report_period,
        dry_run=body.dry_run,
        skip_telegram=body.skip_telegram,
        skip_sheet=body.skip_sheet,
        trigger='manual',
    )
    return ResponseEnvelope(status='success', data=asdict(result))


# ── History query (spec-006 C-1 / C-2) ─────────────────────────────────────


_DEFAULT_HISTORY_LOOKBACK_DAYS = 365


def _decimal_to_float(value: Decimal | None) -> float | None:
    """Convert a ``Decimal`` to ``float`` for JSON serialization.

    The history endpoint returns price/PnL series intended for charts; consumers
    do not perform exact arithmetic on the response, so a ``float`` round-trip
    is acceptable and keeps the JSON payload small / chart-friendly.

    Args:
        value: Decimal value or ``None``.

    Returns:
        ``float(value)`` when set, ``None`` otherwise.
    """
    return float(value) if value is not None else None


def _captured_at_iso(value: datetime) -> str:
    """Serialize ``captured_at`` to ISO 8601, defaulting naive values to Asia/Taipei.

    Production data on Postgres ``TIMESTAMPTZ`` is always tz-aware; the fallback
    only matters for dialects (e.g. SQLite under tests) that drop tzinfo on read.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo('Asia/Taipei'))
    return value.isoformat()


def _serialize_symbol_snapshot(row: SymbolSnapshot) -> dict[str, Any]:
    """Project a :class:`SymbolSnapshot` into the API response shape."""
    return {
        'report_period': row.report_period,
        'shares': _decimal_to_float(row.shares),
        'avg_cost': _decimal_to_float(row.avg_cost),
        'current_price': _decimal_to_float(row.current_price),
        'market_value': _decimal_to_float(row.market_value),
        'unrealized_pnl': _decimal_to_float(row.unrealized_pnl),
        'pnl_pct': _decimal_to_float(row.pnl_pct),
        'pnl_delta': _decimal_to_float(row.pnl_delta),
        'captured_at': _captured_at_iso(row.captured_at),
    }


def _serialize_summary_dual(row: ReportSummary) -> dict[str, Any]:
    """Project a :class:`ReportSummary` row for the dual-market response."""
    return {
        'report_period': row.report_period,
        'pnl_tw_total': _decimal_to_float(row.pnl_tw_total),
        'pnl_us_total': _decimal_to_float(row.pnl_us_total),
        'pnl_tw_delta': _decimal_to_float(row.pnl_tw_delta),
        'pnl_us_delta': _decimal_to_float(row.pnl_us_delta),
        'buy_amount_twd': _decimal_to_float(row.buy_amount_twd),
        'signals_count': row.signals_count,
        'symbols_count': row.symbols_count,
        'captured_at': _captured_at_iso(row.captured_at),
    }


def _serialize_summary_single(
    row: ReportSummary,
    market: Literal['TW', 'US'],
) -> dict[str, Any]:
    """Project a :class:`ReportSummary` row, collapsing to a single market.

    The dual TW/US PnL columns collapse to ``pnl_total`` / ``pnl_delta`` and
    the opposite-market fields are hidden so the response stays focused.
    """
    if market == 'TW':
        pnl_total = row.pnl_tw_total
        pnl_delta = row.pnl_tw_delta
    else:
        pnl_total = row.pnl_us_total
        pnl_delta = row.pnl_us_delta
    return {
        'report_period': row.report_period,
        'pnl_total': _decimal_to_float(pnl_total),
        'pnl_delta': _decimal_to_float(pnl_delta),
        'buy_amount_twd': _decimal_to_float(row.buy_amount_twd),
        'signals_count': row.signals_count,
        'symbols_count': row.symbols_count,
        'captured_at': _captured_at_iso(row.captured_at),
    }


def _resolve_history_window(
    since: date | None,
    until: date | None,
) -> tuple[date, date]:
    """Apply default 1-year window and validate ``since <= until``.

    Args:
        since: Caller-supplied lower bound; defaults to ``today - 365 days``.
        until: Caller-supplied upper bound; defaults to ``today``.

    Returns:
        Resolved ``(since, until)`` tuple.

    Raises:
        HTTPException: 400 when ``since > until``.
    """
    today = datetime.now(_TZ).date()
    resolved_until = until or today
    resolved_since = since or (today - timedelta(days=_DEFAULT_HISTORY_LOOKBACK_DAYS))
    if resolved_since > resolved_until:
        raise HTTPException(status_code=400, detail='since must be <= until')
    return resolved_since, resolved_until


def _query_symbol_history(
    *,
    symbol: str,
    market: Literal['TW', 'US'],
    report_type: Literal['weekly', 'monthly'],
    since: date,
    until: date,
    limit: int,
) -> dict[str, Any]:
    """Run the per-symbol time-series query and build the response payload."""
    rows = report_history_repo.list_symbol_history(
        symbol=symbol,
        market=market,
        report_type=report_type,
        since=since,
        until=until,
        limit=limit,
    )
    return {
        'mode': 'symbol',
        'symbol': symbol,
        'market': market,
        'report_type': report_type,
        'records': [_serialize_symbol_snapshot(r) for r in rows],
    }


def _query_summary_history(
    *,
    market: Literal['TW', 'US'] | None,
    report_type: Literal['weekly', 'monthly'],
    since: date,
    until: date,
    limit: int,
) -> dict[str, Any]:
    """Run the summary time-series query and build the response payload."""
    rows = report_history_repo.list_summary_history(
        report_type=report_type,
        market=market,
        since=since,
        until=until,
        limit=limit,
    )
    if market is None:
        records = [_serialize_summary_dual(r) for r in rows]
        markets: list[str] = ['TW', 'US']
    else:
        records = [_serialize_summary_single(r, market) for r in rows]
        markets = [market]
    return {
        'mode': 'summary',
        'markets': markets,
        'report_type': report_type,
        'records': records,
    }


@router.get(
    '/history',
    response_model=ResponseEnvelope[dict[str, Any]],
    summary='Query persisted weekly/monthly report history',
)
async def get_history(
    symbol: Annotated[str | None, Query()] = None,
    market: Annotated[Literal['TW', 'US'] | None, Query()] = None,
    report_type: Annotated[Literal['weekly', 'monthly'], Query()] = 'monthly',
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> ResponseEnvelope[dict[str, Any]]:
    """Return per-symbol or summary history for a date window (spec-006 C-1).

    Three branches:

    * ``symbol`` + ``market`` → per-symbol time series (mode=``symbol``).
    * ``market`` only → single-market summary (mode=``summary``, one market).
    * Neither → dual-market summary (mode=``summary``, both markets).

    Args:
        symbol: Optional ticker. Requires ``market`` when supplied.
        market: ``'TW'`` or ``'US'``; required if ``symbol`` is given.
        report_type: ``'weekly'`` or ``'monthly'``.
        since: Inclusive lower bound (defaults to one year ago).
        until: Inclusive upper bound (defaults to today).
        limit: Row cap (1-1000, default 100).

    Returns:
        ResponseEnvelope wrapping ``data.mode`` plus mode-specific keys.

    Raises:
        HTTPException: 400 when ``symbol`` is given without ``market``,
            or when ``since > until``.
    """
    if symbol is not None and market is None:
        raise HTTPException(
            status_code=400,
            detail='market is required when symbol is provided',
        )
    resolved_since, resolved_until = _resolve_history_window(since, until)
    if symbol is not None and market is not None:
        data = _query_symbol_history(
            symbol=symbol,
            market=market,
            report_type=report_type,
            since=resolved_since,
            until=resolved_until,
            limit=limit,
        )
    else:
        data = _query_summary_history(
            market=market,
            report_type=report_type,
            since=resolved_since,
            until=resolved_until,
            limit=limit,
        )
    logger.info(
        'report_history.api.query mode=%s symbol=%s market=%s '
        'report_type=%s records=%d',
        data['mode'],
        symbol,
        market,
        report_type,
        len(data['records']),
    )
    return ResponseEnvelope(status='success', data=data)


@router.get(
    '/history/options',
    response_model=ResponseEnvelope[dict[str, Any]],
    summary='UI selector metadata for /history (markets / symbols / periods)',
)
async def get_history_options() -> ResponseEnvelope[dict[str, Any]]:
    """Return the cached options payload from the repository (spec-006 C-2).

    The repository wraps a Redis cache (TTL 600s) — we do no extra work here.
    """
    payload = report_history_repo.list_options()
    return ResponseEnvelope(status='success', data=dict(payload))
