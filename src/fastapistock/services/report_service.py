"""Weekly and monthly portfolio report builder + sender.

Both reports are pure text (MarkdownV2) messages delivered through the
Telegram Bot HTTP API.  Section rendering is defensive: any data source that
fails returns a specific placeholder so the rest of the report still gets sent.

The :func:`run_report_pipeline` entry point composes the full build → Telegram
push → Postgres UPSERT → Sheet append flow used by cron, manual trigger, and
backfill callers (spec-006 Phase 3, functionality G).
"""

from __future__ import annotations

import calendar
import logging
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal, NamedTuple, TypeVar
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.exc import SQLAlchemyError

from fastapistock import config
from fastapistock.repositories import (
    portfolio_repo,
    portfolio_snapshot_repo,
    report_history_repo,
    sheet_writer,
    signal_history_repo,
    transactions_repo,
)
from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.repositories.portfolio_snapshot_repo import PortfolioSnapshot
from fastapistock.repositories.report_history_repo import ReportSummary, SymbolSnapshot
from fastapistock.repositories.signal_history_repo import SignalRecord
from fastapistock.services.telegram_service import _escape_md

logger = logging.getLogger(__name__)
_pipeline_logger = logging.getLogger('fastapistock.report_history')

_TZ: ZoneInfo = ZoneInfo('Asia/Taipei')
_TELEGRAM_API_BASE = 'https://api.telegram.org'
_REQUEST_TIMEOUT = 10
_TIER_TO_STARS: dict[int, str] = {1: '⭐', 2: '⭐⭐', 3: '⭐⭐⭐'}

ReportType = Literal['weekly', 'monthly']
Trigger = Literal['cron', 'manual', 'backfill']

_PERIOD_PATTERN = re.compile(r'^\d{4}-\d{2}(-\d{2})?$')


# ── data containers ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _ReportWindow:
    """Date window + title label for a single report run."""

    start: date
    end: date
    title: str  # e.g. 'Weekly 2026-04-19 ~ 2026-04-25'
    snapshot_key: str  # 'weekly' or 'monthly'
    snapshot_id: str  # YYYY-MM-DD or YYYY-MM
    prev_snapshot_id: str
    # 'week' or 'month' used when labelling "本週/本月"
    period_label: str
    # month used for sum_buy_amount (target month of the report)
    target_year: int
    target_month: int


@dataclass(frozen=True)
class _FetchResults:
    """Raw data collected once per pipeline run, shared by build + persist."""

    pnl_tw: float | None
    pnl_us: float | None
    portfolio_tw: dict[str, PortfolioEntry]
    portfolio_us: dict[str, PortfolioEntry]
    signals: list[SignalRecord]
    buy_amount: float | None
    prev_snapshot: PortfolioSnapshot | None
    prev_failed: bool
    now: datetime


@dataclass(frozen=True)
class RunReportResult:
    """Outcome of a single ``run_report_pipeline`` invocation."""

    job_id: str
    report_type: ReportType
    report_period: str
    trigger: Trigger
    dry_run: bool
    telegram_sent: bool
    postgres_ok: bool
    sheet_ok: bool | None
    symbol_rows_written: int
    summary_written: bool
    duration_ms: int
    errors: list[str] = field(default_factory=list)


# ── helpers ────────────────────────────────────────────────────────────────


def _weekly_window(now: datetime) -> _ReportWindow:
    """Compute the weekly report window ending on the most recent Sunday.

    The report always covers Monday~Sunday of the just-finished ISO week. The
    window end is pinned to ``monday + 6`` (Sunday) so a scheduler that slips
    past midnight — firing at e.g. Monday 00:00:01 — still publishes the prior
    week's report rather than skipping to the new week. ``prev_snapshot_id``
    is the Sunday before that Monday.
    """
    local = now.astimezone(_TZ)
    today = local.date()
    # Anchor to the most recent Sunday at or before ``today``: Sunday=6 weekday.
    days_since_sunday = (today.weekday() + 1) % 7
    sunday = today - timedelta(days=days_since_sunday)
    monday = sunday - timedelta(days=6)
    prev_sunday = monday - timedelta(days=1)
    return _ReportWindow(
        start=monday,
        end=sunday,
        title=f'週報 {monday.isoformat()} ~ {sunday.isoformat()}',
        snapshot_key='weekly',
        snapshot_id=sunday.isoformat(),
        prev_snapshot_id=prev_sunday.isoformat(),
        period_label='本週',
        target_year=today.year,
        target_month=today.month,
    )


def _monthly_window(now: datetime) -> _ReportWindow:
    """Compute the monthly report window covering the month before *now*."""
    local = now.astimezone(_TZ)
    first_of_this_month = local.date().replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1)
    prev_month_id = first_of_prev_month.strftime('%Y-%m')
    # Previous monthly snapshot is the month before that
    prev_prev_last = first_of_prev_month - timedelta(days=1)
    prev_prev_month_id = prev_prev_last.strftime('%Y-%m')
    return _ReportWindow(
        start=first_of_prev_month,
        end=last_of_prev_month,
        title=f'月報 {prev_month_id}',
        snapshot_key='monthly',
        snapshot_id=prev_month_id,
        prev_snapshot_id=prev_prev_month_id,
        period_label='本月',
        target_year=first_of_prev_month.year,
        target_month=first_of_prev_month.month,
    )


def _fmt_signed_int(value: float) -> str:
    """Format *value* as thousand-separated integer with explicit sign."""
    sign = '+' if value >= 0 else '-'
    return f'{sign}{abs(value):,.0f}'


class _PrevSnapshotResult(NamedTuple):
    """Result of attempting to load the previous-period snapshot.

    Attributes:
        snapshot: The loaded snapshot, or None when none exists / load failed.
        failed: True when the underlying Redis call raised an exception.
            When False and *snapshot* is None, the key simply does not exist
            (first-run / no prior baseline).
    """

    snapshot: PortfolioSnapshot | None
    failed: bool


def _load_prev_snapshot(window: _ReportWindow) -> _PrevSnapshotResult:
    """Fetch the previous-period snapshot for *window*.

    Returns:
        A ``_PrevSnapshotResult`` whose ``failed`` flag is True when the
        underlying Redis call raised, so callers can distinguish between
        "first run" (no baseline yet) and "load failure" (transient error).
    """
    try:
        if window.snapshot_key == 'weekly':
            snapshot = portfolio_snapshot_repo.get_weekly(window.prev_snapshot_id)
        else:
            snapshot = portfolio_snapshot_repo.get_monthly(window.prev_snapshot_id)
        return _PrevSnapshotResult(snapshot=snapshot, failed=False)
    except Exception as exc:
        logger.warning('load_prev_snapshot failed: %s', exc)
        return _PrevSnapshotResult(snapshot=None, failed=True)


def _save_current_snapshot(window: _ReportWindow, snapshot: PortfolioSnapshot) -> None:
    """Persist *snapshot* under the appropriate key for *window*."""
    if window.snapshot_key == 'weekly':
        portfolio_snapshot_repo.save_weekly(snapshot)
    else:
        portfolio_snapshot_repo.save_monthly(snapshot)


def _pct_change(current: float, previous: float) -> float | None:
    """Return percentage change from *previous* to *current*; None on zero prev."""
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def _format_currency_delta(delta: float, currency: str) -> str:
    """Format a signed currency delta, e.g. '+23,456 TWD'."""
    return f'{_fmt_signed_int(delta)} {currency}'


def _render_position_section(
    window: _ReportWindow,
    pnl_tw: float | None,
    pnl_us: float | None,
    prev: PortfolioSnapshot | None,
    prev_failed: bool = False,
) -> list[str]:
    """Produce the MarkdownV2 lines for the "position change" section.

    Args:
        window: Report window metadata (period label etc.).
        pnl_tw: Current TW pnl, or None when repo fetch failed.
        pnl_us: Current US pnl, or None when repo fetch failed.
        prev: Previously persisted snapshot, or None when absent / unreadable.
        prev_failed: True when the prev-snapshot lookup itself raised;
            distinguishes transient failure from legitimate first-run state.
    """
    header = f'── {window.period_label}部位變化 ──'
    lines: list[str] = [_escape_md(header)]

    if pnl_tw is None and pnl_us is None:
        lines.append(_escape_md('資料讀取失敗'))
        return lines

    if prev_failed:
        lines.append(_escape_md('快照讀取失敗'))
    elif prev is None:
        lines.append(_escape_md('首次執行，尚無對比基準'))
    else:
        tw_delta = (pnl_tw or 0.0) - prev.pnl_tw
        us_delta = (pnl_us or 0.0) - prev.pnl_us
        tw_pct = _pct_change(pnl_tw or 0.0, prev.pnl_tw)
        us_pct = _pct_change(pnl_us or 0.0, prev.pnl_us)
        tw_pct_txt = (
            f' ({window.period_label} {tw_pct:+.1f}%)' if tw_pct is not None else ''
        )
        us_pct_txt = (
            f' ({window.period_label} {us_pct:+.1f}%)' if us_pct is not None else ''
        )
        lines.append(
            _escape_md(f'台股: {_format_currency_delta(tw_delta, "TWD")}{tw_pct_txt}')
        )
        lines.append(
            _escape_md(f'美股: {_format_currency_delta(us_delta, "TWD")}{us_pct_txt}')
        )

    current_tw = '資料讀取失敗' if pnl_tw is None else f'{_fmt_signed_int(pnl_tw)} TWD'
    current_us = '資料讀取失敗' if pnl_us is None else f'{_fmt_signed_int(pnl_us)} TWD'
    lines.append(_escape_md(f'當前總損益: 台股 {current_tw} | 美股 {current_us}'))
    return lines


def _format_signal_trajectory(records: list[SignalRecord]) -> list[str]:
    """Group *records* by symbol, sort by timestamp, return one line per symbol.

    Example outputs::

        '2330: ⭐⭐ (4/15) → ⭐⭐⭐ (4/22)'
        '0050: ⭐ (4/18)'
    """
    grouped: dict[str, list[SignalRecord]] = defaultdict(list)
    for rec in records:
        grouped[rec.symbol].append(rec)

    lines: list[str] = []
    for symbol in sorted(grouped.keys()):
        items = sorted(grouped[symbol], key=lambda r: r.timestamp)
        tokens: list[str] = []
        for rec in items:
            stars = _TIER_TO_STARS.get(rec.tier, '⭐' * max(rec.tier, 1))
            day = rec.timestamp.astimezone(_TZ)
            tokens.append(f'{stars} ({day.month}/{day.day})')
        lines.append(f'{symbol}: {" → ".join(tokens)}')
    return lines


def _render_signal_section(
    window: _ReportWindow, records: list[SignalRecord]
) -> list[str]:
    """Produce MarkdownV2 lines for the "signals" section."""
    header = f'── {window.period_label}加碼訊號 ──'
    lines: list[str] = [_escape_md(header)]

    if not records:
        lines.append(_escape_md(f'{window.period_label}無觸發加碼訊號'))
        return lines

    for raw_line in _format_signal_trajectory(records):
        lines.append(_escape_md(raw_line))

    max_tier = max(r.tier for r in records)
    stars = _TIER_TO_STARS.get(max_tier, '⭐' * max(max_tier, 1))
    distinct = len({r.symbol for r in records})
    lines.append(_escape_md(f'（共觸發 {distinct} 檔，最嚴重 {stars}）'))
    return lines


def _render_investment_section(
    window: _ReportWindow, buy_amount: float | None
) -> list[str]:
    """Produce MarkdownV2 lines for the "regular investment progress" section."""
    is_weekly = window.snapshot_key == 'weekly'
    header_prefix = '本月定額進度' if is_weekly else '本月定額達成'
    lines: list[str] = [_escape_md(f'── {header_prefix} ──')]

    if buy_amount is None:
        lines.append(_escape_md('資料讀取失敗'))
        return lines

    target = config.REGULAR_INVESTMENT_TARGET_TWD
    pct = (buy_amount / target * 100) if target > 0 else 0.0
    label = '本月已買入' if window.snapshot_key == 'weekly' else '實際投入'
    lines.append(_escape_md(f'{label}: {buy_amount:,.0f} / {target:,} TWD'))
    tail = ' ✅' if pct >= 100 else ''
    lines.append(_escape_md(f'達成率: {pct:.0f}%{tail}'))
    return lines


_T = TypeVar('_T')


def _safe_call(label: str, func: Callable[[], _T]) -> _T | None:
    """Invoke *func* and return its result, or None when it raises."""
    try:
        return func()
    except Exception as exc:
        logger.warning('%s failed: %s', label, exc)
        return None


def _collect_fetch_results(window: _ReportWindow, now: datetime) -> _FetchResults:
    """Run every external read once for the given window.

    The returned :class:`_FetchResults` is shared between the markdown render
    path and the Postgres / Sheet persistence path so external services are
    only hit a single time per pipeline invocation.
    """
    pnl_tw = _safe_call('fetch_pnl_tw', portfolio_repo.fetch_pnl_tw)
    pnl_us = _safe_call('fetch_pnl_us', portfolio_repo.fetch_pnl_us)
    portfolio_tw_raw = _safe_call('fetch_portfolio_tw', portfolio_repo.fetch_portfolio)
    portfolio_us_raw = _safe_call(
        'fetch_portfolio_us', portfolio_repo.fetch_portfolio_us
    )
    prev_result = _load_prev_snapshot(window)
    signals_raw = _safe_call(
        'list_signals',
        lambda: signal_history_repo.list_signals(window.start, window.end),
    )
    buy_amount = _safe_call(
        'sum_buy_amount',
        lambda: transactions_repo.sum_buy_amount(
            window.target_year, window.target_month
        ),
    )
    return _FetchResults(
        pnl_tw=pnl_tw,
        pnl_us=pnl_us,
        portfolio_tw=portfolio_tw_raw or {},
        portfolio_us=portfolio_us_raw or {},
        signals=signals_raw if signals_raw is not None else [],
        buy_amount=buy_amount,
        prev_snapshot=prev_result.snapshot,
        prev_failed=prev_result.failed,
        now=now,
    )


def _persist_redis_snapshot(
    window: _ReportWindow, fetch_results: _FetchResults
) -> None:
    """Persist the current period's snapshot for next run's diff (best-effort)."""
    pnl_tw = fetch_results.pnl_tw
    pnl_us = fetch_results.pnl_us
    if pnl_tw is None and pnl_us is None:
        return
    snapshot = PortfolioSnapshot(
        pnl_tw=pnl_tw if pnl_tw is not None else 0.0,
        pnl_us=pnl_us if pnl_us is not None else 0.0,
        timestamp=_snapshot_timestamp(window, fetch_results.now),
    )
    try:
        _save_current_snapshot(window, snapshot)
    except Exception as exc:
        logger.warning('save current snapshot failed: %s', exc)


def _build_report(window: _ReportWindow, now: datetime) -> tuple[str, _FetchResults]:
    """Compose the MarkdownV2 report string and return it with raw fetches."""
    fetch_results = _collect_fetch_results(window, now)

    sep = '\\-' * 25
    title_esc = _escape_md(window.title)
    lines: list[str] = [f'📊 *{title_esc}*', sep, '']
    lines += _render_position_section(
        window,
        fetch_results.pnl_tw,
        fetch_results.pnl_us,
        fetch_results.prev_snapshot,
        prev_failed=fetch_results.prev_failed,
    )
    lines.append('')
    lines += _render_signal_section(window, fetch_results.signals)
    lines.append('')
    lines += _render_investment_section(window, fetch_results.buy_amount)
    lines.append('')
    lines += [sep, '_由 FastAPI Stock Bot 自動產生_']

    return '\n'.join(lines), fetch_results


def _snapshot_timestamp(window: _ReportWindow, now: datetime) -> datetime:
    """Return the timestamp used when persisting the current snapshot.

    Monthly snapshots are deliberately anchored to the final day of the target
    month at 21:00 Asia/Taipei, regardless of when the scheduler actually fires.
    This fixed anchor makes subsequent sorting and cross-month comparison
    trivial (keys always fall on YYYY-MM-last-day). Weekly snapshots use the
    actual execution time (*now*) so the stored timestamp reflects when the
    data was captured.
    """
    local = now.astimezone(_TZ)
    if window.snapshot_key == 'weekly':
        return local
    # monthly: anchor at last-day-of-target-month 21:00 for stable ordering
    year = window.target_year
    month = window.target_month
    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, last_day, 21, 0, tzinfo=_TZ)


def build_weekly_report(now: datetime) -> tuple[str, _FetchResults]:
    """Build the weekly MarkdownV2 report string anchored at *now*.

    Returns:
        Tuple of (markdown_text, fetch_results) so callers (the pipeline) can
        reuse the raw fetch payload without paying for a second round-trip.
    """
    return _build_report(_weekly_window(now), now)


def build_monthly_report(now: datetime) -> tuple[str, _FetchResults]:
    """Build the monthly MarkdownV2 report string anchored at *now*."""
    return _build_report(_monthly_window(now), now)


def _send_markdown(text: str) -> bool:
    """Send *text* (MarkdownV2) to the configured TELEGRAM_USER_ID."""
    if not config.TELEGRAM_TOKEN:
        logger.error('TELEGRAM_TOKEN is not configured; report not sent')
        return False
    if not config.TELEGRAM_USER_ID:
        logger.error('TELEGRAM_USER_ID is not configured; report not sent')
        return False

    url = f'{_TELEGRAM_API_BASE}/bot{config.TELEGRAM_TOKEN}/sendMessage'
    payload = {
        'chat_id': config.TELEGRAM_USER_ID,
        'text': text,
        'parse_mode': 'MarkdownV2',
    }
    try:
        response = httpx.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            'Telegram API error while sending report: %s %s',
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except httpx.RequestError as exc:
        logger.error('Telegram request failed while sending report: %s', exc)
        return False


# ── Decimal-conversion helpers ─────────────────────────────────────────────


def _to_decimal(value: float | int) -> Decimal:
    """Convert a numeric value to ``Decimal`` via its ``str`` form.

    Uses ``Decimal(str(...))`` to avoid binary float drift that
    ``Decimal(float)`` would introduce.
    """
    return Decimal(str(value))


def _fetch_current_price(market: str, symbol: str) -> Decimal | None:
    """Resolve the current price for one symbol via the appropriate service.

    TW codes go through :func:`stock_service.get_rich_tw_stocks`; US tickers
    through :func:`us_stock_service.get_us_stocks`.  Any failure returns
    ``None`` and is logged at WARNING so the caller can skip the symbol.
    """
    try:
        if market == 'TW':
            from fastapistock.services.stock_service import get_rich_tw_stocks

            stocks = get_rich_tw_stocks([symbol])
        elif market == 'US':
            from fastapistock.services.us_stock_service import get_us_stocks

            stocks = get_us_stocks([symbol])
        else:
            return None
    except Exception as exc:
        logger.warning('fetch_current_price failed for %s/%s: %s', market, symbol, exc)
        return None
    if not stocks:
        return None
    return _to_decimal(stocks[0].price)


def _select_portfolio(
    fetch_results: _FetchResults, market: str
) -> dict[str, PortfolioEntry]:
    """Return the portfolio mapping for *market* from collected fetch results."""
    if market == 'TW':
        return fetch_results.portfolio_tw
    if market == 'US':
        return fetch_results.portfolio_us
    return {}


def _make_symbol_snapshot(
    *,
    window: _ReportWindow,
    market: str,
    entry: PortfolioEntry,
    current_price: Decimal,
    captured_at: datetime,
) -> SymbolSnapshot:
    """Compose a single :class:`SymbolSnapshot` row using Decimal arithmetic."""
    shares = _to_decimal(entry.shares)
    avg_cost = _to_decimal(entry.avg_cost)
    unrealized_pnl = _to_decimal(entry.unrealized_pnl)
    market_value = shares * current_price
    cost_basis = shares * avg_cost
    pnl_pct: Decimal | None = None
    if cost_basis != 0:
        pnl_pct = unrealized_pnl / cost_basis * Decimal('100')
    return SymbolSnapshot(
        report_type=window.snapshot_key,
        report_period=window.snapshot_id,
        market=market,
        symbol=entry.symbol,
        shares=shares,
        avg_cost=avg_cost,
        current_price=current_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        pnl_pct=pnl_pct,
        pnl_delta=None,  # per-symbol delta requires prev-period symbol rows; future
        captured_at=captured_at,
    )


def _build_symbol_snapshots(
    window: _ReportWindow, fetch_results: _FetchResults, market: str
) -> list[SymbolSnapshot]:
    """Assemble :class:`SymbolSnapshot` rows for one market.

    Per-symbol price-fetch failures are skipped (logged) so a single bad
    ticker cannot block the whole report.
    """
    portfolio = _select_portfolio(fetch_results, market)
    if not portfolio:
        return []
    captured_at = _snapshot_timestamp(window, fetch_results.now)
    rows: list[SymbolSnapshot] = []
    for symbol in sorted(portfolio.keys()):
        entry = portfolio[symbol]
        current_price = _fetch_current_price(market, symbol)
        if current_price is None:
            continue
        rows.append(
            _make_symbol_snapshot(
                window=window,
                market=market,
                entry=entry,
                current_price=current_price,
                captured_at=captured_at,
            )
        )
    return rows


def _build_summary(
    window: _ReportWindow,
    fetch_results: _FetchResults,
    snapshot_rows: list[SymbolSnapshot],
) -> ReportSummary | None:
    """Compose the per-period :class:`ReportSummary`, or ``None`` on missing PnL.

    When either ``pnl_tw`` or ``pnl_us`` is missing we deliberately skip the
    summary write rather than persisting a zero placeholder that would
    pollute the historical baseline.
    """
    if fetch_results.pnl_tw is None or fetch_results.pnl_us is None:
        return None
    pnl_tw_total = _to_decimal(fetch_results.pnl_tw)
    pnl_us_total = _to_decimal(fetch_results.pnl_us)
    pnl_tw_delta: Decimal | None = None
    pnl_us_delta: Decimal | None = None
    prev = fetch_results.prev_snapshot
    if prev is not None:
        pnl_tw_delta = pnl_tw_total - _to_decimal(prev.pnl_tw)
        pnl_us_delta = pnl_us_total - _to_decimal(prev.pnl_us)
    buy_amount_twd: Decimal | None = (
        _to_decimal(fetch_results.buy_amount)
        if fetch_results.buy_amount is not None
        else None
    )
    return ReportSummary(
        report_type=window.snapshot_key,
        report_period=window.snapshot_id,
        pnl_tw_total=pnl_tw_total,
        pnl_us_total=pnl_us_total,
        pnl_tw_delta=pnl_tw_delta,
        pnl_us_delta=pnl_us_delta,
        buy_amount_twd=buy_amount_twd,
        signals_count=len(fetch_results.signals),
        symbols_count=len(snapshot_rows),
        captured_at=_snapshot_timestamp(window, fetch_results.now),
    )


# ── pipeline ───────────────────────────────────────────────────────────────


def _resolve_window(
    *,
    report_type: ReportType,
    report_period: str | None,
    now: datetime,
) -> _ReportWindow:
    """Build a ``_ReportWindow`` honouring an explicit ``report_period`` override.

    Raises:
        ValueError: When ``report_period`` is provided but does not match the
            ``YYYY-MM`` / ``YYYY-MM-DD`` shape required by the storage layer.
    """
    if report_period is not None and not _PERIOD_PATTERN.fullmatch(report_period):
        raise ValueError(
            f'Invalid report_period: {report_period!r}; expected YYYY-MM or YYYY-MM-DD'
        )
    base = _weekly_window(now) if report_type == 'weekly' else _monthly_window(now)
    if report_period is None:
        return base
    return _ReportWindow(
        start=base.start,
        end=base.end,
        title=base.title,
        snapshot_key=base.snapshot_key,
        snapshot_id=report_period,
        prev_snapshot_id=base.prev_snapshot_id,
        period_label=base.period_label,
        target_year=base.target_year,
        target_month=base.target_month,
    )


def _run_telegram_step(
    *,
    skip_telegram: bool,
    markdown: str,
    log: logging.LoggerAdapter[logging.Logger],
) -> bool:
    """Run the Telegram push step; returns ``telegram_sent`` flag."""
    if skip_telegram:
        log.info('report_history.build.telegram.skipped')
        return False
    try:
        ok = _send_markdown(markdown)
    except Exception as exc:  # defensive: _send_markdown should not raise
        log.warning(
            'report_history.build.telegram.fail',
            extra={'error_type': type(exc).__name__, 'error_message': str(exc)},
        )
        return False
    if ok:
        log.info('report_history.build.telegram.ok')
        return True
    log.warning(
        'report_history.build.telegram.fail',
        extra={'error_type': 'send_failed'},
    )
    return False


@dataclass
class _PostgresStepResult:
    """Outcome of the Postgres UPSERT step."""

    postgres_ok: bool
    rows_written: int
    summary_written: bool
    errors: list[str]


def _run_postgres_step(
    *,
    snapshots: list[SymbolSnapshot],
    summary: ReportSummary | None,
    summary_skipped: bool,
    log: logging.LoggerAdapter[logging.Logger],
) -> _PostgresStepResult:
    """Persist snapshots + summary; never raises."""
    errors: list[str] = []
    if summary_skipped:
        errors.append('pnl_fetch_failed')
    try:
        rows_written = report_history_repo.upsert_symbol_snapshots(snapshots)
        if summary is not None:
            report_history_repo.upsert_report_summary(summary)
            summary_written = True
        else:
            summary_written = False
        return _PostgresStepResult(
            postgres_ok=True,
            rows_written=rows_written,
            summary_written=summary_written,
            errors=errors,
        )
    except SQLAlchemyError as exc:
        log.error(
            'report_history.build.postgres.fail',
            extra={
                'error_type': type(exc).__name__,
                'error_message': str(exc),
            },
        )
        errors.append('SQLAlchemyError')
        return _PostgresStepResult(
            postgres_ok=False,
            rows_written=0,
            summary_written=False,
            errors=errors,
        )


def _run_sheet_step(
    *,
    report_type: ReportType,
    skip_sheet: bool,
    tw_snapshots: list[SymbolSnapshot],
    us_snapshots: list[SymbolSnapshot],
    log: logging.LoggerAdapter[logging.Logger],
) -> bool | None:
    """Run the monthly Sheet append step; returns the ``sheet_ok`` flag.

    Weekly reports and ``skip_sheet=True`` short-circuit to ``None`` so the
    caller can record "not applicable" instead of a misleading boolean.
    """
    if report_type != 'monthly' or skip_sheet:
        log.info(
            'report_history.build.sheet.skipped',
            extra={'reason': 'weekly' if report_type != 'monthly' else 'skip_sheet'},
        )
        return None
    tw_ok = sheet_writer.append_monthly_history('TW', tw_snapshots)
    us_ok = sheet_writer.append_monthly_history('US', us_snapshots)
    return tw_ok and us_ok


def run_report_pipeline(
    *,
    report_type: ReportType,
    report_period: str | None = None,
    trigger: Trigger = 'cron',
    dry_run: bool = False,
    skip_telegram: bool = False,
    skip_sheet: bool = False,
    now: datetime | None = None,
) -> RunReportResult:
    """Execute one build → Telegram → Postgres → Sheet flow.

    The pipeline never raises: every recoverable failure is captured into
    :attr:`RunReportResult.errors` and emitted via the structured logger so a
    single transient outage cannot stop the scheduler.

    Args:
        report_type: ``'weekly'`` or ``'monthly'``.
        report_period: Optional explicit period label; auto-derived when
            ``None``.  Validated against ``^\\d{4}-\\d{2}(-\\d{2})?$``.
        trigger: Caller identity used purely for log/observability tagging.
        dry_run: When True, build markdown only and skip every side effect.
        skip_telegram: When True, suppress the Telegram push.
        skip_sheet: When True, suppress the Sheet append (monthly only).
        now: Override of "now" for deterministic tests; defaults to
            ``datetime.now(_TZ)``.

    Returns:
        :class:`RunReportResult` summarising every persistence side-effect.

    Raises:
        ValueError: If ``report_period`` is malformed.  This is the only
            exception escape hatch: it surfaces caller bugs (manual
            trigger / backfill scripts) rather than runtime failures.
    """
    start = time.monotonic()
    job_id = uuid.uuid4().hex[:8]
    effective_now = now if now is not None else datetime.now(_TZ)
    window = _resolve_window(
        report_type=report_type, report_period=report_period, now=effective_now
    )
    log = logging.LoggerAdapter(
        _pipeline_logger,
        extra={
            'job_id': job_id,
            'trigger': trigger,
            'report_type': report_type,
            'report_period': window.snapshot_id,
        },
    )
    log.info('report_history.build.start')

    markdown, fetch_results = _build_report(window, effective_now)

    if dry_run:
        log.info(
            'report_history.build.dry_run_preview',
            extra={'preview': markdown[:200]},
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return RunReportResult(
            job_id=job_id,
            report_type=report_type,
            report_period=window.snapshot_id,
            trigger=trigger,
            dry_run=True,
            telegram_sent=False,
            postgres_ok=False,
            sheet_ok=None,
            symbol_rows_written=0,
            summary_written=False,
            duration_ms=duration_ms,
            errors=[],
        )

    # Step 1 — Telegram (failure does not block subsequent steps).
    telegram_sent = _run_telegram_step(
        skip_telegram=skip_telegram, markdown=markdown, log=log
    )
    _persist_redis_snapshot(window, fetch_results)

    # Step 2 — Postgres (failure does not block sheet step).
    tw_snapshots = _build_symbol_snapshots(window, fetch_results, 'TW')
    us_snapshots = _build_symbol_snapshots(window, fetch_results, 'US')
    all_snapshots = tw_snapshots + us_snapshots
    summary = _build_summary(window, fetch_results, all_snapshots)
    summary_skipped = fetch_results.pnl_tw is None or fetch_results.pnl_us is None
    pg_result = _run_postgres_step(
        snapshots=all_snapshots,
        summary=summary,
        summary_skipped=summary_skipped,
        log=log,
    )

    # Step 3 — Sheet (monthly only).
    sheet_ok = _run_sheet_step(
        report_type=report_type,
        skip_sheet=skip_sheet,
        tw_snapshots=tw_snapshots,
        us_snapshots=us_snapshots,
        log=log,
    )

    duration_ms = int((time.monotonic() - start) * 1000)
    log.info(
        'report_history.build.done',
        extra={
            'postgres_ok': pg_result.postgres_ok,
            'sheet_ok': sheet_ok,
            'telegram_sent': telegram_sent,
            'symbol_rows_written': pg_result.rows_written,
            'summary_written': pg_result.summary_written,
            'duration_ms': duration_ms,
            'errors': pg_result.errors,
        },
    )
    return RunReportResult(
        job_id=job_id,
        report_type=report_type,
        report_period=window.snapshot_id,
        trigger=trigger,
        dry_run=False,
        telegram_sent=telegram_sent,
        postgres_ok=pg_result.postgres_ok,
        sheet_ok=sheet_ok,
        symbol_rows_written=pg_result.rows_written,
        summary_written=pg_result.summary_written,
        duration_ms=duration_ms,
        errors=pg_result.errors,
    )
