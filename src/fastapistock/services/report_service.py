"""Weekly and monthly portfolio report builder + sender.

Both reports are pure text (MarkdownV2) messages delivered through the
Telegram Bot HTTP API.  Section rendering is defensive: any data source that
fails returns a specific placeholder so the rest of the report still gets sent.
"""

from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import NamedTuple, TypeVar
from zoneinfo import ZoneInfo

import httpx

from fastapistock import config
from fastapistock.repositories import (
    portfolio_repo,
    portfolio_snapshot_repo,
    signal_history_repo,
    transactions_repo,
)
from fastapistock.repositories.portfolio_snapshot_repo import PortfolioSnapshot
from fastapistock.repositories.signal_history_repo import SignalRecord
from fastapistock.services.telegram_service import _escape_md

logger = logging.getLogger(__name__)

_TZ: ZoneInfo = ZoneInfo('Asia/Taipei')
_TELEGRAM_API_BASE = 'https://api.telegram.org'
_REQUEST_TIMEOUT = 10
_TIER_TO_STARS: dict[int, str] = {1: '⭐', 2: '⭐⭐', 3: '⭐⭐⭐'}


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
            _escape_md(f'美股: {_format_currency_delta(us_delta, "USD")}{us_pct_txt}')
        )

    current_tw = '資料讀取失敗' if pnl_tw is None else f'{_fmt_signed_int(pnl_tw)} TWD'
    current_us = '資料讀取失敗' if pnl_us is None else f'{_fmt_signed_int(pnl_us)} USD'
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


def _build_report(window: _ReportWindow, now: datetime) -> str:
    """Compose the full MarkdownV2 report string for *window*."""
    pnl_tw = _safe_call('fetch_pnl_tw', portfolio_repo.fetch_pnl_tw)
    pnl_us = _safe_call('fetch_pnl_us', portfolio_repo.fetch_pnl_us)
    prev_result = _load_prev_snapshot(window)
    prev_snapshot = prev_result.snapshot
    prev_failed = prev_result.failed

    signals_raw = _safe_call(
        'list_signals',
        lambda: signal_history_repo.list_signals(window.start, window.end),
    )
    signals: list[SignalRecord] = signals_raw if signals_raw is not None else []

    buy_amount: float | None
    try:
        buy_amount = transactions_repo.sum_buy_amount(
            window.target_year, window.target_month
        )
    except Exception as exc:
        logger.warning('sum_buy_amount failed: %s', exc)
        buy_amount = None

    sep = '\\-' * 25
    title_esc = _escape_md(window.title)
    lines: list[str] = [f'📊 *{title_esc}*', sep, '']
    lines += _render_position_section(
        window, pnl_tw, pnl_us, prev_snapshot, prev_failed=prev_failed
    )
    lines.append('')
    lines += _render_signal_section(window, signals)
    lines.append('')
    lines += _render_investment_section(window, buy_amount)
    lines.append('')
    lines += [sep, '_由 FastAPI Stock Bot 自動產生_']

    # Persist current snapshot for next run (best-effort).
    if pnl_tw is not None or pnl_us is not None:
        snapshot = PortfolioSnapshot(
            pnl_tw=pnl_tw if pnl_tw is not None else 0.0,
            pnl_us=pnl_us if pnl_us is not None else 0.0,
            timestamp=_snapshot_timestamp(window, now),
        )
        try:
            _save_current_snapshot(window, snapshot)
        except Exception as exc:
            logger.warning('save current snapshot failed: %s', exc)

    return '\n'.join(lines)


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


def build_weekly_report(now: datetime) -> str:
    """Build the weekly MarkdownV2 report string anchored at *now*."""
    return _build_report(_weekly_window(now), now)


def build_monthly_report(now: datetime) -> str:
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


def send_weekly_report() -> None:
    """Build and send the weekly report.  Never raises."""
    try:
        now = datetime.now(_TZ)
        text = build_weekly_report(now)
        ok = _send_markdown(text)
        logger.info('Weekly report sent=%s', ok)
    except Exception:
        logger.exception('send_weekly_report failed')


def send_monthly_report() -> None:
    """Build and send the monthly report.  Never raises."""
    try:
        now = datetime.now(_TZ)
        text = build_monthly_report(now)
        ok = _send_markdown(text)
        logger.info('Monthly report sent=%s', ok)
    except Exception:
        logger.exception('send_monthly_report failed')
