"""Repository for reading quarterly investment plan data from Google Sheets CSV export.

Sheet column mapping (GID configured via GOOGLE_SHEETS_INVESTMENT_PLAN_GID):
    A (index 0): Stock symbol
    B (index 1): Quarter start date
    C (index 2): Quarter end date
    F (index 5): Expected investment amount (USD)
    G (index 6): Already invested amount (USD)
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date

import httpx

from fastapistock import config

logger = logging.getLogger(__name__)

# Lazy import to avoid circular; injected at call time
from fastapistock.cache import redis_cache  # noqa: E402

_SHEETS_CSV_URL = (
    'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
)

_COL_SYMBOL = 0
_COL_START = 1
_COL_END = 2
_COL_EXPECTED = 5
_COL_INVESTED = 6
_MIN_COLS = 7  # need at least 7 columns (index 0–6)

_DATE_FORMATS = ('%Y-%m-%d', '%Y/%m/%d')

_CACHE_KEY_PREFIX = 'investment_plan'


@dataclass(frozen=True)
class InvestmentPlanEntry:
    """A single row from the quarterly investment plan sheet.

    Attributes:
        symbol: Stock ticker symbol (e.g. 'AAPL').
        start_date: Quarter start date (inclusive).
        end_date: Quarter end date (inclusive).
        expected_usd: Expected investment amount in USD.
        invested_usd: Amount already invested in USD.
    """

    symbol: str
    start_date: date
    end_date: date
    expected_usd: float
    invested_usd: float


def _parse_date(raw: str) -> date | None:
    """Attempt to parse a date string using known formats.

    Args:
        raw: Raw cell value such as '2026-04-01' or '2026/04/01'.

    Returns:
        Parsed date, or None if all formats fail.
    """
    from datetime import datetime

    stripped = raw.strip()
    if not stripped:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(raw: str) -> float:
    """Convert a raw cell string to float, stripping thousand-separators.

    Args:
        raw: Raw cell value such as '1,000.00' or ''.

    Returns:
        Parsed float; 0.0 for empty or blank strings.
    """
    stripped = raw.strip().replace(',', '')
    if not stripped:
        return 0.0
    return float(stripped)


def _entry_to_dict(entry: InvestmentPlanEntry) -> dict[str, object]:
    """Serialise an InvestmentPlanEntry to a JSON-safe dict for Redis.

    Args:
        entry: InvestmentPlanEntry to serialise.

    Returns:
        Dict with ISO-formatted date strings.
    """
    return {
        'symbol': entry.symbol,
        'start_date': entry.start_date.isoformat(),
        'end_date': entry.end_date.isoformat(),
        'expected_usd': entry.expected_usd,
        'invested_usd': entry.invested_usd,
    }


def _dict_to_entry(data: dict[str, object]) -> InvestmentPlanEntry | None:
    """Deserialise a cached dict back to InvestmentPlanEntry.

    Args:
        data: Dict previously produced by _entry_to_dict.

    Returns:
        InvestmentPlanEntry, or None if parsing fails.
    """
    try:
        start = _parse_date(str(data['start_date']))
        end = _parse_date(str(data['end_date']))
        if start is None or end is None:
            return None
        return InvestmentPlanEntry(
            symbol=str(data['symbol']),
            start_date=start,
            end_date=end,
            expected_usd=float(data['expected_usd']),  # type: ignore[arg-type]
            invested_usd=float(data['invested_usd']),  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning('Failed to deserialise cached entry: %s', exc)
        return None


def _fetch_live(sheet_id: str, gid: str) -> list[InvestmentPlanEntry]:
    """Fetch and parse the investment plan CSV directly from Google Sheets.

    Args:
        sheet_id: Google Sheets document ID.
        gid: Worksheet GID.

    Returns:
        List of parsed InvestmentPlanEntry objects; empty list on error.
    """
    url = _SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    logger.info('Fetching investment plan from Google Sheets gid=%s', gid)

    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error('HTTP error fetching investment plan: %s', exc)
        return []
    except httpx.RequestError as exc:
        logger.error('Request error fetching investment plan: %s', exc)
        return []

    entries: list[InvestmentPlanEntry] = []
    reader = csv.reader(io.StringIO(response.text))

    for row_index, row in enumerate(reader):
        if row_index == 0:
            continue  # skip header row
        if len(row) < _MIN_COLS:
            continue

        symbol = row[_COL_SYMBOL].strip()
        if not symbol:
            continue

        start_date = _parse_date(row[_COL_START])
        end_date = _parse_date(row[_COL_END])
        if start_date is None or end_date is None:
            logger.warning('Skipping row %d: unparseable dates', row_index)
            continue

        try:
            expected = _parse_number(row[_COL_EXPECTED])
            invested = _parse_number(row[_COL_INVESTED])
        except ValueError as exc:
            logger.warning('Skipping row %d: %s', row_index, exc)
            continue

        if expected == 0.0 and invested == 0.0:
            continue  # skip placeholder rows

        entries.append(
            InvestmentPlanEntry(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                expected_usd=expected,
                invested_usd=invested,
            )
        )

    return entries


def fetch_investment_plan(today: date) -> list[InvestmentPlanEntry]:
    """Return the quarterly investment plan, using Redis cache when available.

    Falls back to a live Google Sheets fetch if the cache is unavailable
    or unpopulated. When Redis is unreachable, fetches live and skips caching.

    Args:
        today: Date used as part of the cache key (``investment_plan:YYYY-MM-DD``).

    Returns:
        List of InvestmentPlanEntry; empty list when configuration is missing
        or all network/parse errors occur.
    """
    sheet_id = config.GOOGLE_SHEETS_ID
    gid = config.GOOGLE_SHEETS_INVESTMENT_PLAN_GID

    if not sheet_id or not gid:
        logger.warning(
            'GOOGLE_SHEETS_ID or GOOGLE_SHEETS_INVESTMENT_PLAN_GID not configured; '
            'investment plan disabled'
        )
        return []

    cache_key = f'{_CACHE_KEY_PREFIX}:{today.isoformat()}'

    # Try cache first (errors treated as miss)
    try:
        cached = redis_cache.get(cache_key)
        if cached is not None:
            raw_list = cached.get('entries', [])
            entries = [
                e
                for raw in (raw_list if isinstance(raw_list, list) else [])
                if isinstance(raw, dict)
                for e in [_dict_to_entry(raw)]
                if e is not None
            ]
            logger.info('Investment plan served from cache (key=%s)', cache_key)
            return entries
    except Exception as exc:  # redis.RedisError or unexpected
        logger.warning(
            'Cache read failed for %s: %s — falling back to live fetch', cache_key, exc
        )

    # Live fetch
    entries = _fetch_live(sheet_id, gid)

    # Store in cache (best-effort; errors are non-fatal)
    if entries:
        try:
            redis_cache.put(
                cache_key,
                {'entries': [_entry_to_dict(e) for e in entries]},
                config.PORTFOLIO_CACHE_TTL,
            )
        except Exception as exc:
            logger.warning('Cache write failed for %s: %s', cache_key, exc)

    return entries
