"""Service for computing quarterly investment achievement rates.

Reads from the investment plan repository, filters rows active for the
given date, and produces a formatted Telegram reply string with both
aggregate totals and per-symbol breakdowns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from fastapistock.repositories.investment_plan_repo import (
    InvestmentPlanEntry,
    fetch_investment_plan,
)

logger = logging.getLogger(__name__)

_BAR_LENGTH = 10


@dataclass(frozen=True)
class SymbolAchievement:
    """Per-symbol investment achievement for the current quarter.

    Attributes:
        symbol: Stock ticker symbol (e.g. 'AAPL').
        rate_pct: Individual achievement rate in percent.
                  Sentinel -1.0 when expected_usd is 0.
        invested_usd: Amount already invested for this symbol (USD).
        expected_usd: Expected investment amount for this symbol (USD).
    """

    symbol: str
    rate_pct: float
    invested_usd: float
    expected_usd: float


@dataclass(frozen=True)
class QuarterlyAchievementReport:
    """Computed result for the quarterly investment achievement rate.

    Attributes:
        rate_pct: Overall achievement percentage (Σ invested / Σ expected × 100).
                  Sentinel value -1.0 indicates the expected total is 0.
        total_invested: Sum of already-invested amounts for the quarter (USD).
        total_expected: Sum of expected investment amounts for the quarter (USD).
        symbols: List of stock tickers active in the current quarter.
        per_symbol: Per-symbol achievement breakdown in the same order as symbols.
        date_range: Human-readable period label (e.g. '2026-04-01 ~ 2026-06-30').
    """

    rate_pct: float
    total_invested: float
    total_expected: float
    symbols: list[str]
    per_symbol: list[SymbolAchievement]
    date_range: str


def _progress_bar(rate_pct: float) -> str:
    """Build a 10-block Unicode progress bar.

    Args:
        rate_pct: Percentage value (may exceed 100).

    Returns:
        String of ▓ (filled) and ░ (empty) blocks.
    """
    filled = min(_BAR_LENGTH, round(rate_pct / _BAR_LENGTH))
    return '▓' * filled + '░' * (_BAR_LENGTH - filled)


def _symbol_rate(entry: InvestmentPlanEntry) -> float:
    """Compute the achievement rate for a single symbol.

    Args:
        entry: InvestmentPlanEntry for the symbol.

    Returns:
        Rate as a percentage, or -1.0 when expected_usd is 0.
    """
    if entry.expected_usd == 0.0:
        return -1.0
    return entry.invested_usd / entry.expected_usd * 100.0


def get_quarterly_achievement_rate(today: date) -> QuarterlyAchievementReport | None:
    """Compute the investment achievement rate for the quarter containing *today*.

    Filters InvestmentPlanEntry rows where start_date ≤ today ≤ end_date and
    at least one of expected_usd / invested_usd is non-zero. Builds both an
    aggregate report and per-symbol breakdowns.

    Args:
        today: Reference date used to select active rows and as cache key.

    Returns:
        QuarterlyAchievementReport if at least one active row is found, else None.
        When the expected total is 0, rate_pct is set to the sentinel -1.0.
    """
    all_entries = fetch_investment_plan(today)

    active: list[InvestmentPlanEntry] = [
        e
        for e in all_entries
        if e.start_date <= today <= e.end_date
        and (e.expected_usd > 0.0 or e.invested_usd > 0.0)
    ]

    if not active:
        logger.info('No active investment plan rows for date=%s', today)
        return None

    total_expected = sum(e.expected_usd for e in active)
    total_invested = sum(e.invested_usd for e in active)
    symbols = [e.symbol for e in active]

    per_symbol = [
        SymbolAchievement(
            symbol=e.symbol,
            rate_pct=_symbol_rate(e),
            invested_usd=e.invested_usd,
            expected_usd=e.expected_usd,
        )
        for e in active
    ]

    min_start = min(e.start_date for e in active)
    max_end = max(e.end_date for e in active)
    date_range = f'{min_start.isoformat()} ~ {max_end.isoformat()}'

    if total_expected == 0.0:
        rate_pct = -1.0
    else:
        rate_pct = total_invested / total_expected * 100.0

    return QuarterlyAchievementReport(
        rate_pct=rate_pct,
        total_invested=total_invested,
        total_expected=total_expected,
        symbols=symbols,
        per_symbol=per_symbol,
        date_range=date_range,
    )


def _format_symbol_row(sa: SymbolAchievement) -> str:
    """Format a single per-symbol achievement row.

    Args:
        sa: SymbolAchievement for one stock.

    Returns:
        Formatted string, e.g. '  AAPL  ▓▓▓▓▓░░░░░  50.00%  ($500/$1,000)'.
    """
    amounts = f'(${sa.invested_usd:,.2f}/${sa.expected_usd:,.2f})'
    if sa.rate_pct == -1.0:
        return f'  {sa.symbol:<6}  {"N/A":<12}  {amounts}'
    bar = _progress_bar(sa.rate_pct)
    return f'  {sa.symbol:<6}  {bar}  {sa.rate_pct:>6.2f}%  {amounts}'


def format_achievement_reply(report: QuarterlyAchievementReport | None) -> str:
    """Format a QuarterlyAchievementReport as a Telegram plain-text reply.

    Includes an aggregate summary and a per-symbol breakdown section.

    Args:
        report: Computed report, or None if no data is available.

    Returns:
        Formatted string ready to send as a Telegram message.
    """
    if report is None:
        return '本季無投資計畫資料'

    if report.rate_pct == -1.0:
        return (
            f'📊 本季投資達成率\n\n'
            f'本季預期投資金額為 0，無法計算達成率\n'
            f'期間：{report.date_range}'
        )

    bar = _progress_bar(report.rate_pct)
    symbol_rows = '\n'.join(_format_symbol_row(sa) for sa in report.per_symbol)

    return (
        f'📊 本季投資達成率\n\n'
        f'整體：{bar} {report.rate_pct:.2f}%\n'
        f'已投入：${report.total_invested:,.2f} / '
        f'預期：${report.total_expected:,.2f} USD\n\n'
        f'📌 個股明細：\n'
        f'{symbol_rows}\n\n'
        f'期間：{report.date_range}'
    )
