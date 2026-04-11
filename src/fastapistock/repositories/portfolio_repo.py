"""Repository for reading personal portfolio data from Google Sheets CSV export."""

import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import date

import httpx

from fastapistock import config
from fastapistock.cache import redis_cache

logger = logging.getLogger(__name__)

_COL_SYMBOL = 0
_COL_SHARES = 2
_COL_AVG_COST = 5
_COL_UNREALIZED_PNL = 8
_COL_US_SHARES = 5
_COL_US_AVG_COST = 6
_COL_US_UNREALIZED_PNL = 7

# PnL summary cells (0-indexed): TW total = I19, US total = H21
_TW_PNL_ROW: int = 18  # Cell I19
_TW_PNL_COL: int = 8  # Column I
_US_PNL_ROW: int = 20  # Cell H21
_US_PNL_COL: int = 7  # Column H

_SHEETS_CSV_URL = (
    'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
)
_PREFIX_RE = re.compile(r'^[A-Za-z]+[_:\-]')


@dataclass(frozen=True)
class PortfolioEntry:
    """Immutable portfolio position for a single stock.

    Attributes:
        symbol: Taiwan stock code (e.g. '2330').
        shares: Number of shares held.
        avg_cost: Average cost per share in TWD.
        unrealized_pnl: Unrealized profit/loss in TWD.
    """

    symbol: str
    shares: int
    avg_cost: float
    unrealized_pnl: float


def _parse_number(raw: str) -> float:
    """Convert a raw cell string to float.

    Handles empty strings, thousand-separator commas, and negative numbers.

    Args:
        raw: Raw cell value such as '1,000', '-75,000', '820.00', or ''.

    Returns:
        Parsed float; returns 0.0 for empty or blank strings.
    """
    stripped = raw.strip().replace(',', '')
    if not stripped:
        return 0.0
    return float(stripped)


def fetch_portfolio() -> dict[str, PortfolioEntry]:
    """Fetch and parse the portfolio from the Google Sheets CSV export.

    Returns an empty dict (with a log warning) when env vars are not set,
    and an empty dict (with a log error) on HTTP or network failures.
    Rows whose symbol column is not numeric are silently skipped.

    Returns:
        Mapping from stock symbol string to PortfolioEntry.
    """
    sheet_id = config.GOOGLE_SHEETS_ID
    gid = config.GOOGLE_SHEETS_PORTFOLIO_GID_TW

    if not sheet_id or not gid:
        logger.warning(
            'GOOGLE_SHEETS_ID or GOOGLE_SHEETS_PORTFOLIO_GID_TW not configured; '
            'portfolio disabled'
        )
        return {}

    url = _SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    logger.info('Fetching portfolio from Google Sheets')

    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error('HTTP error fetching portfolio: %s', exc)
        return {}
    except httpx.RequestError as exc:
        logger.error('Request error fetching portfolio: %s', exc)
        return {}

    portfolio: dict[str, PortfolioEntry] = {}
    reader = csv.reader(io.StringIO(response.text))

    for row_index, row in enumerate(reader):
        if row_index == 0:
            continue  # skip header row
        if len(row) <= _COL_UNREALIZED_PNL:
            continue
        symbol_raw = row[_COL_SYMBOL].strip()
        if not symbol_raw.isdigit():
            continue  # skip subtotal rows and blank rows

        try:
            entry = PortfolioEntry(
                symbol=symbol_raw,
                shares=int(_parse_number(row[_COL_SHARES])),
                avg_cost=_parse_number(row[_COL_AVG_COST]),
                unrealized_pnl=_parse_number(row[_COL_UNREALIZED_PNL]),
            )
        except (ValueError, IndexError) as exc:
            logger.warning('Skipping malformed portfolio row %d: %s', row_index, exc)
            continue

        portfolio[symbol_raw] = entry

    return portfolio


def _normalize_us_symbol(raw: str) -> str:
    """Normalize prefixed US symbol text to a ticker.

    Args:
        raw: Raw symbol string from sheet column A, e.g. 'US_AAPL'.

    Returns:
        Normalized uppercase ticker (e.g. 'AAPL').
    """
    symbol = raw.strip().upper()
    if not symbol:
        return ''
    symbol = _PREFIX_RE.sub('', symbol)
    return symbol


def fetch_portfolio_us() -> dict[str, PortfolioEntry]:
    """Fetch and parse US portfolio rows from Google Sheets CSV export.

    Expected US mapping:
        A: Symbol with prefix
        F: Shares
        G: Average cost
        H: Unrealized PnL

    Returns:
        Mapping from normalized ticker to PortfolioEntry.
    """
    sheet_id = config.GOOGLE_SHEETS_ID
    gid = config.GOOGLE_SHEETS_PORTFOLIO_GID_US

    if not sheet_id or not gid:
        logger.warning(
            'GOOGLE_SHEETS_ID or GOOGLE_SHEETS_PORTFOLIO_GID_US not configured; '
            'US portfolio disabled'
        )
        return {}

    url = _SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    logger.info('Fetching US portfolio from Google Sheets')

    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error('HTTP error fetching US portfolio: %s', exc)
        return {}
    except httpx.RequestError as exc:
        logger.error('Request error fetching US portfolio: %s', exc)
        return {}

    portfolio: dict[str, PortfolioEntry] = {}
    reader = csv.reader(io.StringIO(response.text))

    for row_index, row in enumerate(reader):
        if row_index == 0:
            continue
        if len(row) <= _COL_US_UNREALIZED_PNL:
            continue
        normalized = _normalize_us_symbol(row[_COL_SYMBOL])
        if not normalized or not normalized.isalpha():
            continue

        try:
            entry = PortfolioEntry(
                symbol=normalized,
                shares=int(_parse_number(row[_COL_US_SHARES])),
                avg_cost=_parse_number(row[_COL_US_AVG_COST]),
                unrealized_pnl=_parse_number(row[_COL_US_UNREALIZED_PNL]),
            )
        except (ValueError, IndexError) as exc:
            logger.warning('Skipping malformed US portfolio row %d: %s', row_index, exc)
            continue

        portfolio[normalized] = entry

    return portfolio


def _fetch_pnl_cell(gid: str, row: int, col: int, cache_key: str) -> float | None:
    """Fetch a single PnL summary cell from a Google Sheets CSV, with Redis cache.

    Args:
        gid: Google Sheets worksheet GID.
        row: 0-indexed row number of the target cell.
        col: 0-indexed column number of the target cell.
        cache_key: Redis key under which the value is cached.

    Returns:
        Parsed float on success (may be negative); None on any error.
    """
    sheet_id = config.GOOGLE_SHEETS_ID
    if not sheet_id or not gid:
        return None

    try:
        cached = redis_cache.get(cache_key)
        if cached is not None:
            logger.info('PnL served from cache (key=%s)', cache_key)
            return float(str(cached['value']))
    except Exception as exc:
        logger.warning(
            'Cache read failed for %s: %s — falling back to live fetch', cache_key, exc
        )

    url = _SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    logger.info('Fetching PnL cell from Google Sheets (key=%s)', cache_key)

    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error('HTTP error fetching PnL: %s', exc)
        return None
    except httpx.RequestError as exc:
        logger.error('Request error fetching PnL: %s', exc)
        return None

    rows = list(csv.reader(io.StringIO(response.text)))
    if row >= len(rows) or col >= len(rows[row]):
        logger.error('PnL cell (%d, %d) out of range in sheet gid=%s', row, col, gid)
        return None

    try:
        value = _parse_number(rows[row][col])
    except ValueError as exc:
        logger.error('Failed to parse PnL cell value: %s', exc)
        return None

    try:
        redis_cache.put(cache_key, {'value': str(value)}, config.PORTFOLIO_CACHE_TTL)
    except Exception as exc:
        logger.warning('Cache write failed for %s: %s', cache_key, exc)

    return value


def fetch_pnl_tw() -> float | None:
    """Fetch the TW portfolio total unrealized PnL from cell I20.

    Uses Redis cache key ``pnl:tw:YYYY-MM-DD`` with TTL ``PORTFOLIO_CACHE_TTL``.
    Falls back to a live Google Sheets CSV fetch on cache miss.

    Returns:
        Total unrealized PnL in TWD (may be negative), or None on error.
    """
    gid = config.GOOGLE_SHEETS_PORTFOLIO_GID_TW
    cache_key = f'pnl:tw:{date.today().isoformat()}'
    return _fetch_pnl_cell(gid, _TW_PNL_ROW, _TW_PNL_COL, cache_key)


def fetch_pnl_us() -> float | None:
    """Fetch the US portfolio total unrealized PnL from cell H21.

    Uses Redis cache key ``pnl:us:YYYY-MM-DD`` with TTL ``PORTFOLIO_CACHE_TTL``.
    Falls back to a live Google Sheets CSV fetch on cache miss.

    Returns:
        Total unrealized PnL in TWD (may be negative), or None on error.
    """
    gid = config.GOOGLE_SHEETS_PORTFOLIO_GID_US
    cache_key = f'pnl:us:{date.today().isoformat()}'
    return _fetch_pnl_cell(gid, _US_PNL_ROW, _US_PNL_COL, cache_key)
