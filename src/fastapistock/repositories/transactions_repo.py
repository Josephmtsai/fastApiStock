"""Repository for reading TW and US transaction records from Google Sheets CSV.

TW sheet column mapping (GID configured via ``GOOGLE_SHEETS_TW_TRANSACTIONS_GID``)::

    A (0): 股名        symbol
    B (1): 日期        date        (YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD)
    C (2): 成交股數    shares
    D (3): 成本        cost
    E (4): 買賣別      action (contains '買' for entry / '賣' for exit;
                                     typical values '現買', '沖買', '現賣', '沖賣')
    F (5): 淨股數      net_shares  (signed)
    G (6): 淨金額      net_amount  (buy is negative, sell positive)
    H (7): 年度        year

US sheet column mapping (GID configured via ``GOOGLE_SHEETS_US_TRANSACTIONS_GID``)::

    A (0): Date              date    (YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD)
    B (1): Ticker            symbol
    C (2): Action Type       action  (e.g. 'Buy', 'Sell')
    D (3): Price             price
    E (4): Shares            shares
    F (5): Net Cash Flow     net_cash_flow
    G (6): Current Stock Price  current_stock_price
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from fastapistock import config
from fastapistock.cache import redis_cache

logger = logging.getLogger(__name__)

_SHEETS_CSV_URL = (
    'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
)

_COL_SYMBOL = 0
_COL_DATE = 1
_COL_SHARES = 2
_COL_COST = 3
_COL_ACTION = 4
_COL_NET_SHARES = 5
_COL_NET_AMOUNT = 6
_COL_YEAR = 7
_MIN_COLS = 8  # need at least 8 columns (index 0–7)

_DATE_FORMATS = ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d')
_BUY_MARKER = '買'


@dataclass(frozen=True)
class Transaction:
    """Immutable single transaction record.

    Attributes:
        symbol: Stock symbol / name.
        date: Execution date.
        shares: Number of shares traded (raw 成交股數).
        cost: Cost per share / total cost column.
        action: Raw 買賣別 cell such as '現買', '沖買', '現賣', '沖賣'
            (pre-stripped).  Entries contain the '買' token; exits contain '賣'.
        net_shares: Net shares (signed per sheet convention).
        net_amount: Net amount (buy negative, sell positive per sheet convention).
        year: Year column as integer.
    """

    symbol: str
    date: date
    shares: float
    cost: float
    action: str
    net_shares: float
    net_amount: float
    year: int


def _parse_number(raw: str) -> float:
    """Convert a raw cell string to float, stripping thousand-separators.

    Args:
        raw: Raw cell value such as '1,000.00', '-75,000', or ''.

    Returns:
        Parsed float; 0.0 for empty / blank strings.
    """
    stripped = raw.strip().replace(',', '')
    if not stripped:
        return 0.0
    return float(stripped)


def _parse_date(raw: str) -> date | None:
    """Parse a date string in any of the supported formats.

    Args:
        raw: Raw cell value such as '2026-04-01', '2026/4/1', or '2026.4.1'.

    Returns:
        Parsed ``date``, or ``None`` when no format matched.
    """
    stripped = raw.strip()
    if not stripped:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None


def _parse_year(raw: str) -> int | None:
    """Parse the year column; fall back to None when unparseable."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return int(float(stripped))
    except ValueError:
        return None


def _parse_row(row_index: int, row: list[str]) -> Transaction | None:
    """Parse a single CSV row into a Transaction, returning None on malformed input."""
    if len(row) < _MIN_COLS:
        return None

    symbol = row[_COL_SYMBOL].strip()
    if not symbol:
        return None

    parsed_date = _parse_date(row[_COL_DATE])
    if parsed_date is None:
        logger.warning(
            'Skipping tx row %d: unparseable date %r', row_index, row[_COL_DATE]
        )
        return None

    action = row[_COL_ACTION].strip()
    if not action:
        logger.warning('Skipping tx row %d: empty action', row_index)
        return None

    year = _parse_year(row[_COL_YEAR])
    if year is None:
        year = parsed_date.year

    try:
        shares = _parse_number(row[_COL_SHARES])
        cost = _parse_number(row[_COL_COST])
        net_shares = _parse_number(row[_COL_NET_SHARES])
        net_amount = _parse_number(row[_COL_NET_AMOUNT])
    except ValueError as exc:
        logger.warning('Skipping tx row %d: %s', row_index, exc)
        return None

    return Transaction(
        symbol=symbol,
        date=parsed_date,
        shares=shares,
        cost=cost,
        action=action,
        net_shares=net_shares,
        net_amount=net_amount,
        year=year,
    )


def fetch_tw_transactions() -> list[Transaction]:
    """Fetch and parse TW transaction records from Google Sheets.

    Returns an empty list (with a warning) when env vars are not configured or
    on any HTTP / network failure.  Malformed rows are skipped with warnings.

    Returns:
        List of parsed Transaction objects, preserving row order.
    """
    sheet_id = config.GOOGLE_SHEETS_ID
    gid = config.GOOGLE_SHEETS_TW_TRANSACTIONS_GID

    if not sheet_id or not gid:
        logger.warning(
            'GOOGLE_SHEETS_ID or GOOGLE_SHEETS_TW_TRANSACTIONS_GID not configured; '
            'TW transactions disabled'
        )
        return []

    url = _SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    logger.info('Fetching TW transactions from Google Sheets')

    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error('HTTP error fetching TW transactions: %s', exc)
        return []
    except httpx.RequestError as exc:
        logger.error('Request error fetching TW transactions: %s', exc)
        return []

    transactions: list[Transaction] = []
    reader = csv.reader(io.StringIO(response.text))

    for row_index, row in enumerate(reader):
        if row_index == 0:
            continue  # skip header row
        tx = _parse_row(row_index, row)
        if tx is not None:
            transactions.append(tx)

    return transactions


_US_COL_DATE = 0
_US_COL_SYMBOL = 1
_US_COL_ACTION = 2
_US_COL_PRICE = 3
_US_COL_SHARES = 4
_US_COL_NET_CASH_FLOW = 5
_US_COL_CURRENT_PRICE = 6
_US_MIN_COLS = 7  # need at least 7 columns (index 0–6)

_EARLIEST_TX_CACHE_TTL = 3600


@dataclass(frozen=True)
class USTransaction:
    """Immutable single US transaction record.

    Attributes:
        symbol: Stock ticker symbol (e.g. 'AAPL').
        date: Execution date.
        action: Raw action cell such as 'Buy', 'Sell'.
        price: Execution price per share.
        shares: Number of shares traded (always positive).
        net_cash_flow: Net cash flow (negative for buys, positive for sells).
        current_stock_price: Current stock price at time of record.
    """

    symbol: str
    date: date
    action: str
    price: float
    shares: float
    net_cash_flow: float
    current_stock_price: float


def _parse_us_row(row_index: int, row: list[str]) -> USTransaction | None:
    """Parse a single US CSV row into a USTransaction.

    Args:
        row_index: 0-based row index (for warning messages).
        row: Raw CSV cells.

    Returns:
        Parsed USTransaction, or None on malformed input.
    """
    if len(row) < _US_MIN_COLS:
        logger.warning(
            'Skipping US tx row %d: too few columns (%d)', row_index, len(row)
        )
        return None

    parsed_date = _parse_date(row[_US_COL_DATE])
    if parsed_date is None:
        logger.warning(
            'Skipping US tx row %d: unparseable date %r', row_index, row[_US_COL_DATE]
        )
        return None

    symbol = row[_US_COL_SYMBOL].strip()
    if not symbol:
        logger.warning('Skipping US tx row %d: empty symbol', row_index)
        return None

    action = row[_US_COL_ACTION].strip()
    if not action:
        logger.warning('Skipping US tx row %d: empty action', row_index)
        return None

    try:
        price = _parse_number(row[_US_COL_PRICE])
        shares = _parse_number(row[_US_COL_SHARES])
        net_cash_flow = _parse_number(row[_US_COL_NET_CASH_FLOW])
        current_stock_price = _parse_number(row[_US_COL_CURRENT_PRICE])
    except ValueError as exc:
        logger.warning('Skipping US tx row %d: %s', row_index, exc)
        return None

    return USTransaction(
        symbol=symbol,
        date=parsed_date,
        action=action,
        price=price,
        shares=shares,
        net_cash_flow=net_cash_flow,
        current_stock_price=current_stock_price,
    )


def fetch_us_transactions() -> list[USTransaction]:
    """Fetch and parse US transaction records from Google Sheets.

    Returns an empty list (with a warning) when env vars are not configured or
    on any HTTP / network failure.  Malformed rows are skipped with warnings.

    Returns:
        List of parsed USTransaction objects, preserving row order.
    """
    sheet_id = config.GOOGLE_SHEETS_ID
    gid = config.GOOGLE_SHEETS_US_TRANSACTIONS_GID

    if not sheet_id or not gid:
        logger.warning(
            'GOOGLE_SHEETS_ID or GOOGLE_SHEETS_US_TRANSACTIONS_GID not configured; '
            'US transactions disabled'
        )
        return []

    url = _SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    logger.info('Fetching US transactions from Google Sheets')

    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error('HTTP error fetching US transactions: %s', exc)
        return []
    except httpx.RequestError as exc:
        logger.error('Request error fetching US transactions: %s', exc)
        return []

    transactions: list[USTransaction] = []
    reader = csv.reader(io.StringIO(response.text))

    for row_index, row in enumerate(reader):
        if row_index == 0:
            continue  # skip header row
        tx = _parse_us_row(row_index, row)
        if tx is not None:
            transactions.append(tx)

    return transactions


def get_earliest_transaction_month(market: str) -> tuple[int, int] | None:
    """Return the (year, month) of the earliest transaction for a given market.

    Results are cached in Redis with TTL 3600 seconds.

    Args:
        market: ``'TW'`` or ``'US'``.

    Returns:
        Tuple ``(year, month)`` of the earliest transaction date, or ``None``
        when no transactions exist or an error occurs.
    """
    cache_key = f'transactions:earliest:{market}'
    try:
        cached = redis_cache.get(cache_key)
        if cached is not None:
            year = int(str(cached['year']))
            month = int(str(cached['month']))
            return (year, month)
    except Exception as exc:
        logger.warning('Cache read failed for key=%s: %s', cache_key, exc)

    try:
        if market == 'TW':
            transactions = fetch_tw_transactions()
            dates = [tx.date for tx in transactions]
        elif market == 'US':
            us_txns = fetch_us_transactions()
            dates = [tx.date for tx in us_txns]
        else:
            logger.warning(
                'Unknown market %r for get_earliest_transaction_month', market
            )
            return None
    except Exception as exc:
        logger.exception('Error fetching transactions for market=%s: %s', market, exc)
        return None

    if not dates:
        return None

    earliest = min(dates)
    result = (earliest.year, earliest.month)

    try:
        redis_cache.put(
            cache_key,
            {'year': result[0], 'month': result[1]},
            _EARLIEST_TX_CACHE_TTL,
        )
    except Exception as exc:
        logger.warning('Cache write failed for key=%s: %s', cache_key, exc)

    return result


def sum_buy_amount(year: int, month: int) -> float:
    """Return the absolute sum of net_amount for BUY transactions in *year*/*month*.

    A transaction is considered a buy (entry) when its ``action`` cell contains
    the '買' token.  This covers all real-world variants seen in the sheet —
    '現買', '沖買', plain '買' — while excluding their sell counterparts
    ('現賣', '沖賣', '賣').

    Args:
        year: Calendar year (4-digit).
        month: Calendar month (1–12).

    Returns:
        Absolute TWD amount bought during the period.  Returns 0.0 when no
        records match or when the transaction repository is unavailable.
    """
    total = 0.0
    for tx in fetch_tw_transactions():
        if _BUY_MARKER not in tx.action.strip():
            continue
        if tx.date.year != year or tx.date.month != month:
            continue
        total += abs(tx.net_amount)
    return total
