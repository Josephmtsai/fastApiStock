"""Standalone CLI script: backfill monthly portfolio history into Postgres + Sheets.

Usage::

    python -m fastapistock.scripts.backfill_history [options]

Options::

    --markets {TW,US,BOTH}   Markets to backfill (default: BOTH)
    --from YYYY-MM            Start month (default: earliest transaction month)
    --to YYYY-MM              End month (default: previous calendar month)
    --repair-deltas           Recalculate pnl_*_delta from DB only
    --dry-run                 Build rows but do not write to DB or Sheet
    --skip-sheet              Skip Google Sheets append
    --symbols SYMBOLS         Comma-separated ticker filter (debug)
    --verbose                 Set log level to DEBUG
"""

from __future__ import annotations

import argparse
import calendar
import logging
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple
from zoneinfo import ZoneInfo

import yfinance

from fastapistock.repositories import (
    sheet_writer,
    transactions_repo,
)
from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
    list_summary_history,
    upsert_report_summary,
    upsert_symbol_snapshots,
)
from fastapistock.repositories.transactions_repo import (
    Transaction,
    USTransaction,
    fetch_tw_transactions,
    fetch_us_transactions,
    get_earliest_transaction_month,
)

logger = logging.getLogger('fastapistock.report_history')

_TW_DELAY_MIN = 1.0
_TW_DELAY_MAX = 2.5
_US_DELAY_MIN = 0.1
_US_DELAY_MAX = 0.3
_TW_BUY_MARKER = '買'
_TAIPEI_TZ = ZoneInfo('Asia/Taipei')
_REPORT_TYPE = 'monthly'


def _build_tw_name_to_code() -> dict[str, str]:
    """Build a Chinese-name → numeric-code lookup dict using twstock.

    TW transactions sheet stores Chinese names (e.g. '元大台灣50') in the
    symbol column.  yfinance requires the numeric code (e.g. '0050').
    Falls back to an empty dict when twstock is unavailable.

    Returns:
        Mapping of stock name to 4-5 digit code string.
    """
    try:
        import twstock  # type: ignore[import-untyped]

        return {info.name: code for code, info in twstock.codes.items()}
    except Exception as exc:
        logger.warning('report_history.backfill.twstock_unavailable: %s', exc)
        return {}


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


class _SymbolPortfolio(NamedTuple):
    """Reconstructed portfolio position for one symbol at a point in time."""

    symbol: str
    current_shares: float
    avg_cost: float


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------


def _fetch_close_price(ticker_str: str, month_end: date) -> float | None:
    """Return the first available closing price on or after month_end.

    Queries yfinance for a 7-day window starting at month_end and returns
    the first non-NaN Close value found.

    Args:
        ticker_str: yfinance ticker string (e.g. '2330.TW', 'AAPL').
        month_end: Last calendar day of the target month.

    Returns:
        Closing price as float, or None when no data is available.
    """
    end_date = month_end + timedelta(days=7)
    try:
        ticker = yfinance.Ticker(ticker_str)
        hist = ticker.history(
            start=month_end.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d'),
        )
        if hist.empty:
            return None
        close_series = hist['Close'].dropna()
        if close_series.empty:
            return None
        return float(close_series.iloc[0])
    except Exception as exc:
        logger.warning(
            'report_history.backfill.price_fetch_fail',
            extra={
                'ticker': ticker_str,
                'error_type': type(exc).__name__,
                'error': str(exc),
            },
        )
        return None


# ---------------------------------------------------------------------------
# Portfolio reconstruction helpers
# ---------------------------------------------------------------------------


def _reconstruct_tw_portfolio(
    transactions: list[Transaction],
    month_end: date,
    filter_symbols: set[str] | None,
) -> list[_SymbolPortfolio]:
    """Reconstruct TW portfolio positions as of month_end.

    Args:
        transactions: Full list of TW transactions.
        month_end: Snapshot date; only transactions on or before this date.
        filter_symbols: When given, restrict to these symbols only.

    Returns:
        List of portfolio positions with positive share counts.
    """
    eligible = [tx for tx in transactions if tx.date <= month_end]
    eligible.sort(key=lambda t: t.date)

    totals: dict[str, dict[str, float]] = {}
    for tx in eligible:
        sym = tx.symbol
        if filter_symbols and sym not in filter_symbols:
            continue
        if sym not in totals:
            totals[sym] = {'buy_shares': 0.0, 'buy_cost': 0.0, 'sell_shares': 0.0}
        if _TW_BUY_MARKER in tx.action:
            totals[sym]['buy_shares'] += abs(tx.net_shares)
            totals[sym]['buy_cost'] += abs(tx.net_amount)
        else:
            totals[sym]['sell_shares'] += abs(tx.net_shares)

    positions: list[_SymbolPortfolio] = []
    for sym, t in totals.items():
        current_shares = t['buy_shares'] - t['sell_shares']
        if current_shares <= 0:
            continue
        avg_cost = t['buy_cost'] / t['buy_shares'] if t['buy_shares'] > 0 else 0.0
        positions.append(_SymbolPortfolio(sym, current_shares, avg_cost))
    return positions


def _reconstruct_us_portfolio(
    transactions: list[USTransaction],
    month_end: date,
    filter_symbols: set[str] | None,
) -> list[_SymbolPortfolio]:
    """Reconstruct US portfolio positions as of month_end.

    Args:
        transactions: Full list of US transactions.
        month_end: Snapshot date; only transactions on or before this date.
        filter_symbols: When given, restrict to these symbols only.

    Returns:
        List of portfolio positions with positive share counts.
    """
    eligible = [tx for tx in transactions if tx.date <= month_end]
    eligible.sort(key=lambda t: t.date)

    totals: dict[str, dict[str, float]] = {}
    for tx in eligible:
        sym = tx.symbol
        if filter_symbols and sym not in filter_symbols:
            continue
        if sym not in totals:
            totals[sym] = {'buy_shares': 0.0, 'buy_cost': 0.0, 'sell_shares': 0.0}
        if 'buy' in tx.action.lower():
            totals[sym]['buy_shares'] += tx.shares
            totals[sym]['buy_cost'] += tx.price * tx.shares
        else:
            totals[sym]['sell_shares'] += tx.shares

    positions: list[_SymbolPortfolio] = []
    for sym, t in totals.items():
        current_shares = t['buy_shares'] - t['sell_shares']
        if current_shares <= 0:
            continue
        avg_cost = t['buy_cost'] / t['buy_shares'] if t['buy_shares'] > 0 else 0.0
        positions.append(_SymbolPortfolio(sym, current_shares, avg_cost))
    return positions


# ---------------------------------------------------------------------------
# Snapshot building
# ---------------------------------------------------------------------------


def _build_tw_snapshots(
    positions: list[_SymbolPortfolio],
    report_period: str,
    month_end: date,
) -> list[SymbolSnapshot]:
    """Fetch prices and build TW SymbolSnapshot rows.

    Args:
        positions: Reconstructed TW portfolio positions.
        report_period: YYYY-MM string for the snapshot period.
        month_end: Last calendar day of the period.

    Returns:
        List of SymbolSnapshot rows for all symbols with a valid price.
    """
    snapshots: list[SymbolSnapshot] = []
    captured_at = datetime(
        month_end.year, month_end.month, month_end.day, 21, 0, tzinfo=_TAIPEI_TZ
    )
    name_to_code = _build_tw_name_to_code()

    for pos in positions:
        code = name_to_code.get(pos.symbol, pos.symbol)
        ticker_str = f'{code}.TW'
        close_price = _fetch_close_price(ticker_str, month_end)
        if close_price is None:
            ticker_str = f'{code}.TWO'
            close_price = _fetch_close_price(ticker_str, month_end)
        if close_price is None:
            logger.warning(
                'report_history.backfill.tw.no_price',
                extra={'symbol': pos.symbol, 'code': code, 'period': report_period},
            )
            continue

        import time as _time

        _time.sleep(random.uniform(_TW_DELAY_MIN, _TW_DELAY_MAX))

        shares_d = Decimal(str(pos.current_shares))
        avg_cost_d = Decimal(str(pos.avg_cost))
        price_d = Decimal(str(close_price))
        market_value = shares_d * price_d
        unrealized_pnl = (price_d - avg_cost_d) * shares_d
        pnl_pct: Decimal | None = None
        if avg_cost_d > Decimal('0'):
            pnl_pct = (price_d - avg_cost_d) / avg_cost_d * Decimal('100')

        snapshots.append(
            SymbolSnapshot(
                report_type=_REPORT_TYPE,
                report_period=report_period,
                market='TW',
                symbol=code,
                shares=shares_d,
                avg_cost=avg_cost_d,
                current_price=price_d,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                pnl_pct=pnl_pct,
                pnl_delta=None,
                captured_at=captured_at,
            )
        )

    return snapshots


def _build_us_snapshots(
    positions: list[_SymbolPortfolio],
    report_period: str,
    month_end: date,
) -> list[SymbolSnapshot]:
    """Fetch prices and build US SymbolSnapshot rows.

    Args:
        positions: Reconstructed US portfolio positions.
        report_period: YYYY-MM string for the snapshot period.
        month_end: Last calendar day of the period.

    Returns:
        List of SymbolSnapshot rows for all symbols with a valid price.
    """
    snapshots: list[SymbolSnapshot] = []
    captured_at = datetime(
        month_end.year, month_end.month, month_end.day, 21, 0, tzinfo=_TAIPEI_TZ
    )

    for pos in positions:
        close_price = _fetch_close_price(pos.symbol, month_end)
        if close_price is None:
            logger.warning(
                'report_history.backfill.us.no_price',
                extra={'symbol': pos.symbol, 'period': report_period},
            )
            continue

        import time as _time

        _time.sleep(random.uniform(_US_DELAY_MIN, _US_DELAY_MAX))

        shares_d = Decimal(str(pos.current_shares))
        avg_cost_d = Decimal(str(pos.avg_cost))
        price_d = Decimal(str(close_price))
        market_value = shares_d * price_d
        unrealized_pnl = (price_d - avg_cost_d) * shares_d
        pnl_pct: Decimal | None = None
        if avg_cost_d > Decimal('0'):
            pnl_pct = (price_d - avg_cost_d) / avg_cost_d * Decimal('100')

        snapshots.append(
            SymbolSnapshot(
                report_type=_REPORT_TYPE,
                report_period=report_period,
                market='US',
                symbol=pos.symbol,
                shares=shares_d,
                avg_cost=avg_cost_d,
                current_price=price_d,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                pnl_pct=pnl_pct,
                pnl_delta=None,
                captured_at=captured_at,
            )
        )

    return snapshots


# ---------------------------------------------------------------------------
# Month backfill
# ---------------------------------------------------------------------------


def _backfill_month(
    market: str,
    year: int,
    month: int,
    *,
    dry_run: bool,
    skip_sheet: bool,
    filter_symbols: set[str] | None,
    verbose: bool,
    prev_tw_total: Decimal | None = None,
    prev_us_total: Decimal | None = None,
) -> tuple[Decimal | None, Decimal | None]:
    """Backfill one market+month combination into DB and optionally Sheets.

    Args:
        market: ``'TW'`` or ``'US'``.
        year: Target year.
        month: Target month (1-12).
        dry_run: When True, build rows but skip DB/Sheet writes.
        skip_sheet: When True, skip Google Sheets append.
        filter_symbols: When given, restrict to these symbols only.
        verbose: When True, log extra debug information.
        prev_tw_total: Previous month's TW PnL total for delta calculation.
        prev_us_total: Previous month's US PnL total for delta calculation.

    Returns:
        Tuple of (new_tw_total, new_us_total) Decimal values (or None).
    """
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    report_period = f'{year:04d}-{month:02d}'

    logger.info(
        'report_history.backfill.month.start',
        extra={'market': market, 'period': report_period},
    )

    tw_snapshots: list[SymbolSnapshot] = []
    us_snapshots: list[SymbolSnapshot] = []

    if market in ('TW', 'BOTH'):
        tw_txns = fetch_tw_transactions()
        tw_positions = _reconstruct_tw_portfolio(tw_txns, month_end, filter_symbols)
        tw_snapshots = _build_tw_snapshots(tw_positions, report_period, month_end)

    if market in ('US', 'BOTH'):
        us_txns = fetch_us_transactions()
        us_positions = _reconstruct_us_portfolio(us_txns, month_end, filter_symbols)
        us_snapshots = _build_us_snapshots(us_positions, report_period, month_end)

    all_snapshots = tw_snapshots + us_snapshots

    pnl_tw_total = Decimal('0')
    pnl_us_total = Decimal('0')
    for snap in tw_snapshots:
        pnl_tw_total += snap.unrealized_pnl
    for snap in us_snapshots:
        pnl_us_total += snap.unrealized_pnl

    pnl_tw_delta: Decimal | None = None
    pnl_us_delta: Decimal | None = None
    if prev_tw_total is not None:
        pnl_tw_delta = pnl_tw_total - prev_tw_total
    if prev_us_total is not None:
        pnl_us_delta = pnl_us_total - prev_us_total

    buy_amount_twd: Decimal | None = None
    if market in ('TW', 'BOTH'):
        raw_buy = transactions_repo.sum_buy_amount(year, month)
        buy_amount_twd = Decimal(str(raw_buy))

    captured_at = datetime(year, month, month_end.day, 21, 0, tzinfo=_TAIPEI_TZ)
    summary = ReportSummary(
        report_type=_REPORT_TYPE,
        report_period=report_period,
        pnl_tw_total=pnl_tw_total,
        pnl_us_total=pnl_us_total,
        pnl_tw_delta=pnl_tw_delta,
        pnl_us_delta=pnl_us_delta,
        buy_amount_twd=buy_amount_twd,
        signals_count=0,
        symbols_count=len(all_snapshots),
        captured_at=captured_at,
    )

    if not dry_run:
        if all_snapshots:
            upsert_symbol_snapshots(all_snapshots)
        upsert_report_summary(summary)

        if not skip_sheet:
            if tw_snapshots:
                sheet_writer.append_monthly_history('TW', tw_snapshots)
            if us_snapshots:
                sheet_writer.append_monthly_history('US', us_snapshots)

    logger.info(
        'report_history.backfill.month.done',
        extra={
            'market': market,
            'period': report_period,
            'tw_symbols': len(tw_snapshots),
            'us_symbols': len(us_snapshots),
            'pnl_tw_total': str(pnl_tw_total),
            'pnl_us_total': str(pnl_us_total),
            'dry_run': dry_run,
        },
    )

    return pnl_tw_total, pnl_us_total


# ---------------------------------------------------------------------------
# Repair deltas
# ---------------------------------------------------------------------------


def _repair_deltas() -> None:
    """Recalculate pnl_tw_delta and pnl_us_delta from existing DB summary rows.

    Reads all monthly summary rows in ascending order, sets the first row's
    deltas to None, and calculates subsequent deltas as the difference from
    the previous row's totals.  Updates each row via UPSERT.
    """
    rows = list_summary_history(
        report_type=_REPORT_TYPE,
        market=None,
        since=date(2000, 1, 1),
        until=date(2099, 12, 31),
        limit=10000,
    )
    logger.info(
        'report_history.backfill.repair_deltas.start',
        extra={'total_rows': len(rows)},
    )

    prev_tw: Decimal | None = None
    prev_us: Decimal | None = None

    for i, row in enumerate(rows):
        if i == 0:
            tw_delta: Decimal | None = None
            us_delta: Decimal | None = None
        else:
            tw_delta = row.pnl_tw_total - prev_tw if prev_tw is not None else None
            us_delta = row.pnl_us_total - prev_us if prev_us is not None else None

        updated = ReportSummary(
            report_type=row.report_type,
            report_period=row.report_period,
            pnl_tw_total=row.pnl_tw_total,
            pnl_us_total=row.pnl_us_total,
            pnl_tw_delta=tw_delta,
            pnl_us_delta=us_delta,
            buy_amount_twd=row.buy_amount_twd,
            signals_count=row.signals_count,
            symbols_count=row.symbols_count,
            captured_at=row.captured_at,
        )
        upsert_report_summary(updated)
        prev_tw = row.pnl_tw_total
        prev_us = row.pnl_us_total

        logger.info(
            'report_history.backfill.repair_deltas.row',
            extra={
                'index': i,
                'period': row.report_period,
                'tw_delta': str(tw_delta),
                'us_delta': str(us_delta),
            },
        )

    logger.info(
        'report_history.backfill.repair_deltas.done',
        extra={'rows_updated': len(rows)},
    )


# ---------------------------------------------------------------------------
# Month range generation
# ---------------------------------------------------------------------------


def _month_range(
    from_year: int, from_month: int, to_year: int, to_month: int
) -> list[tuple[int, int]]:
    """Generate (year, month) tuples from from_date to to_date inclusive.

    Args:
        from_year: Start year.
        from_month: Start month (1-12).
        to_year: End year.
        to_month: End month (1-12).

    Returns:
        Ordered list of (year, month) tuples.
    """
    months: list[tuple[int, int]] = []
    y, m = from_year, from_month
    while (y, m) <= (to_year, to_month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _prev_month_from_today() -> tuple[int, int]:
    """Return (year, month) of the previous calendar month (Asia/Taipei time).

    Returns:
        Tuple of (year, month).
    """
    today = datetime.now(tz=_TAIPEI_TZ).date()
    first_of_this = today.replace(day=1)
    prev = first_of_this - timedelta(days=1)
    return (prev.year, prev.month)


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def _parse_year_month(value: str) -> tuple[int, int]:
    """Parse a YYYY-MM string into (year, month).

    Args:
        value: String in ``YYYY-MM`` format.

    Returns:
        Tuple of (year, month).

    Raises:
        argparse.ArgumentTypeError: When the format is invalid.
    """
    try:
        dt = datetime.strptime(value, '%Y-%m')
        return (dt.year, dt.month)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Invalid YYYY-MM value: {value!r}') from exc


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description='Backfill monthly portfolio history into Postgres + Google Sheets',
        prog='python -m fastapistock.scripts.backfill_history',
    )
    parser.add_argument(
        '--markets',
        choices=['TW', 'US', 'BOTH'],
        default='BOTH',
        help='Markets to backfill (default: BOTH)',
    )
    parser.add_argument(
        '--from',
        dest='from_date',
        metavar='YYYY-MM',
        type=_parse_year_month,
        default=None,
        help='Start month (default: earliest transaction month)',
    )
    parser.add_argument(
        '--to',
        dest='to_date',
        metavar='YYYY-MM',
        type=_parse_year_month,
        default=None,
        help='End month (default: previous calendar month)',
    )
    parser.add_argument(
        '--repair-deltas',
        action='store_true',
        default=False,
        help='Recalculate pnl_*_delta from DB (mutually exclusive with --from/--to)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='Build rows but do not write to DB or Sheet',
    )
    parser.add_argument(
        '--skip-sheet',
        action='store_true',
        default=False,
        help='Skip Google Sheets append',
    )
    parser.add_argument(
        '--symbols',
        default=None,
        help='Comma-separated ticker filter (debug)',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=False,
        help='Set log level to DEBUG',
    )
    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the backfill script.

    Args:
        argv: Argument list; defaults to sys.argv[1:].

    Returns:
        Exit code (0 = success, 1 = fatal error).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    # Initialise DB engine eagerly so we get a clear error if DATABASE_URL is absent
    try:
        from fastapistock.db.engine import get_engine

        get_engine()
    except RuntimeError as exc:
        logger.error('report_history.backfill.db_init_fail: %s', exc)
        return 1

    logger.info('report_history.backfill.start', extra={'cli_args': vars(args)})

    # --repair-deltas mode
    if args.repair_deltas:
        if args.from_date or args.to_date or args.dry_run:
            logger.error(
                'report_history.backfill.invalid_args: '
                '--repair-deltas is mutually exclusive with --from/--to/--dry-run'
            )
            return 1
        _repair_deltas()
        logger.info('report_history.backfill.done')
        return 0

    # Normal backfill mode
    filter_symbols: set[str] | None = None
    if args.symbols:
        filter_symbols = {
            s.strip().upper() for s in args.symbols.split(',') if s.strip()
        }

    markets: list[str]
    if args.markets == 'BOTH':
        markets = ['TW', 'US']
    else:
        markets = [args.markets]

    to_year, to_month = args.to_date if args.to_date else _prev_month_from_today()

    prev_tw_total: Decimal | None = None
    prev_us_total: Decimal | None = None

    for market in markets:
        if args.from_date:
            from_year, from_month = args.from_date
        else:
            earliest = get_earliest_transaction_month(market)
            if earliest is None:
                logger.warning(
                    'report_history.backfill.no_transactions',
                    extra={'market': market},
                )
                continue
            from_year, from_month = earliest

        month_list = _month_range(from_year, from_month, to_year, to_month)
        logger.info(
            'report_history.backfill.market.start',
            extra={'market': market, 'months': len(month_list)},
        )

        for year, month in month_list:
            new_tw, new_us = _backfill_month(
                market,
                year,
                month,
                dry_run=args.dry_run,
                skip_sheet=args.skip_sheet,
                filter_symbols=filter_symbols,
                verbose=args.verbose,
                prev_tw_total=prev_tw_total,
                prev_us_total=prev_us_total,
            )
            prev_tw_total = new_tw
            prev_us_total = new_us

    logger.info('report_history.backfill.done')
    return 0


if __name__ == '__main__':
    sys.exit(main())
