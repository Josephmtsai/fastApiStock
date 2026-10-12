"""Repository for reading personal portfolio data from Google Sheets CSV export."""

import csv
import io
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import httpx

from fastapistock import config
from fastapistock.cache import redis_cache

logger = logging.getLogger(__name__)

_COL_SYMBOL = 0
_COL_SHARES = 2
_COL_BUY_TOTAL = 3  # Column D: total buy amount
_COL_SELL_TOTAL = 4  # Column E: total sell amount
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
        if len(row) <= _COL_SHARES:
            continue
        symbol_raw = row[_COL_SYMBOL].strip()
        if not symbol_raw.isdigit():
            continue  # skip subtotal rows and blank rows

        try:
            entry = PortfolioEntry(
                symbol=symbol_raw,
                shares=int(_parse_number(row[_COL_SHARES])),
                avg_cost=(
                    _parse_number(row[_COL_AVG_COST])
                    if len(row) > _COL_AVG_COST
                    else 0.0
                ),
                unrealized_pnl=(
                    _parse_number(row[_COL_UNREALIZED_PNL])
                    if len(row) > _COL_UNREALIZED_PNL
                    else 0.0
                ),
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
        if len(row) <= _COL_US_SHARES:
            continue
        normalized = _normalize_us_symbol(row[_COL_SYMBOL])
        if not normalized or not normalized.isalpha():
            continue

        try:
            entry = PortfolioEntry(
                symbol=normalized,
                shares=int(_parse_number(row[_COL_US_SHARES])),
                avg_cost=(
                    _parse_number(row[_COL_US_AVG_COST])
                    if len(row) > _COL_US_AVG_COST
                    else 0.0
                ),
                unrealized_pnl=(
                    _parse_number(row[_COL_US_UNREALIZED_PNL])
                    if len(row) > _COL_US_UNREALIZED_PNL
                    else 0.0
                ),
            )
        except (ValueError, IndexError) as exc:
            logger.warning('Skipping malformed US portfolio row %d: %s', row_index, exc)
            continue

        portfolio[normalized] = entry

    return portfolio


def _parse_optional_number(raw: str) -> float | None:
    """Parse a cell; return None for blank or non-numeric (e.g. '#N/A') values.

    Args:
        raw: Raw cell value such as '1,234', '-5', '#N/A', or ''.

    Returns:
        Parsed float, or None when the cell is blank or not numeric.
    """
    stripped = raw.strip().replace(',', '')
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _cell(row: list[str], col: int) -> str:
    """Return the raw text at *col* of *row*, or '' when the column is missing.

    Args:
        row: Parsed CSV row.
        col: 0-indexed column number.

    Returns:
        Raw cell text, or an empty string when out of range.
    """
    return row[col] if len(row) > col else ''


def _fetch_tw_live_price(symbol: str) -> float | None:
    """Return a live TW price via stock_service.get_rich_tw_stock (lazy import).

    Args:
        symbol: Taiwan stock code (e.g. '0050').

    Returns:
        Positive finite price, or None (with a WARNING log) when the lookup
        raises any exception or the price is NaN / not finite / <= 0.
    """
    # Lazy import: stock_service imports this module at module level, so a
    # module-level import here would create a circular import.
    from fastapistock.services.stock_service import get_rich_tw_stock

    try:
        price = float(get_rich_tw_stock(symbol).price)
    except Exception as exc:
        logger.warning('TW live price unavailable for %s: %s', symbol, exc)
        return None
    if not math.isfinite(price) or price <= 0:
        logger.warning('TW live price invalid for %s: %s', symbol, price)
        return None
    return price


def _recompute_na_row(row: list[str], symbol: str, shares: float) -> float | None:
    """Recompute unrealized PnL for one holding row as ``shares*price-(D-E)``.

    Blank D/E cells are treated as 0.

    Args:
        row: Parsed CSV row of the holding.
        symbol: Taiwan stock code of the row.
        shares: Number of shares held (> 0).

    Returns:
        Recomputed unrealized PnL, or None when D/E is non-numeric or the live
        price is unavailable.
    """
    buy_raw = _cell(row, _COL_BUY_TOTAL)
    sell_raw = _cell(row, _COL_SELL_TOTAL)
    buy = _parse_optional_number(buy_raw)
    sell = _parse_optional_number(sell_raw)
    if (buy is None and buy_raw.strip()) or (sell is None and sell_raw.strip()):
        logger.warning('TW PnL fallback: buy/sell total unparseable for %s', symbol)
        return None
    price = _fetch_tw_live_price(symbol)
    if price is None:
        return None
    return shares * price - ((buy or 0.0) - (sell or 0.0))


_NaRow = tuple[list[str], str, float]


def _scan_tw_holdings(
    rows: list[list[str]],
) -> tuple[float, int, list[str], list[_NaRow]]:
    """Scan TW holding rows (between header and summary row).

    Args:
        rows: Full parsed CSV rows of the TW sheet.

    Returns:
        Tuple of (sum of numeric column-I values, number of holdings with
        shares > 0, symbols with unparseable shares, rows needing recompute
        as ``(row, symbol, shares)``).
    """
    total = 0.0
    holdings = 0
    failed: list[str] = []
    na_rows: list[_NaRow] = []
    for row in rows[1:_TW_PNL_ROW]:
        symbol = _cell(row, _COL_SYMBOL).strip()
        if not symbol or len(row) <= _COL_SHARES:
            continue
        shares_raw = row[_COL_SHARES]
        shares = _parse_optional_number(shares_raw)
        if shares is None and shares_raw.strip():
            failed.append(symbol)
            continue
        if shares is None or shares <= 0:
            continue
        holdings += 1
        pnl = _parse_optional_number(_cell(row, _COL_UNREALIZED_PNL))
        if pnl is None:
            na_rows.append((row, symbol, shares))
        else:
            total += pnl
    return total, holdings, failed, na_rows


def _recompute_tw_pnl(rows: list[list[str]], summary_raw: str) -> float | None:
    """Recompute TW total unrealized PnL row-by-row when the summary cell is invalid.

    Holding rows (shares > 0) with a numeric column I are used as-is, even if
    inconsistent with ``H-(D-E)``; rows whose column I is not numeric are
    recomputed from a live price. Rows with shares <= 0 are ignored.

    Args:
        rows: Full parsed CSV rows of the TW sheet.
        summary_raw: Raw text of the summary cell (for logging only).

    Returns:
        Sum of per-holding unrealized PnL, or None when any needed value is
        unavailable or no holding row exists.
    """
    total, holdings, failed, na_rows = _scan_tw_holdings(rows)
    logger.warning(
        'TW PnL summary cell unparseable (%r); using row-by-row fallback, '
        'N/A symbols: %s',
        summary_raw,
        [symbol for _, symbol, _ in na_rows],
    )
    for row, symbol, shares in na_rows:
        recomputed = _recompute_na_row(row, symbol, shares)
        if recomputed is None:
            failed.append(symbol)
        else:
            total += recomputed
    if failed:
        logger.warning('TW PnL fallback failed; unavailable symbols: %s', failed)
        return None
    if holdings == 0:
        logger.warning('TW PnL fallback found no holding rows')
        return None
    return total


def _download_csv_rows(gid: str) -> list[list[str]] | None:
    """Download a Google Sheets worksheet as CSV and parse it into rows.

    Args:
        gid: Google Sheets worksheet GID.

    Returns:
        Parsed CSV rows, or None on HTTP / network errors.
    """
    url = _SHEETS_CSV_URL.format(sheet_id=config.GOOGLE_SHEETS_ID, gid=gid)
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error('HTTP error fetching PnL: %s', exc)
        return None
    except httpx.RequestError as exc:
        logger.error('Request error fetching PnL: %s', exc)
        return None
    return list(csv.reader(io.StringIO(response.text)))


def _fetch_pnl_cell(
    gid: str,
    row: int,
    col: int,
    cache_key: str,
    fallback: Callable[[list[list[str]], str], float | None] | None = None,
) -> float | None:
    """Fetch a single PnL summary cell from a Google Sheets CSV, with Redis cache.

    Args:
        gid: Google Sheets worksheet GID.
        row: 0-indexed row number of the target cell.
        col: 0-indexed column number of the target cell.
        cache_key: Redis key under which the value is cached.
        fallback: Optional callable ``(rows, raw_cell) -> float | None`` invoked
            when the target cell cannot be parsed. Its result is returned
            without being written to the cache.

    Returns:
        Parsed float on success (may be negative); None on any error.
    """
    if not config.GOOGLE_SHEETS_ID or not gid:
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

    logger.info('Fetching PnL cell from Google Sheets (key=%s)', cache_key)
    rows = _download_csv_rows(gid)
    if rows is None:
        return None
    if row >= len(rows) or col >= len(rows[row]):
        logger.error('PnL cell (%d, %d) out of range in sheet gid=%s', row, col, gid)
        return None

    try:
        value = _parse_number(rows[row][col])
    except ValueError as exc:
        if fallback is not None:
            return fallback(rows, rows[row][col])
        logger.error('Failed to parse PnL cell value: %s', exc)
        return None

    try:
        redis_cache.put(cache_key, {'value': str(value)}, config.PORTFOLIO_CACHE_TTL)
    except Exception as exc:
        logger.warning('Cache write failed for %s: %s', cache_key, exc)

    return value


def fetch_pnl_tw() -> float | None:
    """Fetch the TW portfolio total unrealized PnL from cell I19.

    Uses Redis cache key ``pnl:tw:YYYY-MM-DD`` with TTL ``PORTFOLIO_CACHE_TTL``.
    Falls back to a live Google Sheets CSV fetch on cache miss. When I19 is not
    numeric (e.g. ``#N/A``), the total is recomputed row-by-row: numeric
    column-I values are used as-is and non-numeric holdings are recomputed
    from a live price. The recomputed value is NOT written to the cache.

    Returns:
        Total unrealized PnL in TWD (may be negative), or None on error.
    """
    gid = config.GOOGLE_SHEETS_PORTFOLIO_GID_TW
    cache_key = f'pnl:tw:{date.today().isoformat()}'
    return _fetch_pnl_cell(
        gid, _TW_PNL_ROW, _TW_PNL_COL, cache_key, fallback=_recompute_tw_pnl
    )


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
