"""Repository for persisting periodic portfolio snapshots in Redis.

Snapshots are written at the end of each weekly/monthly report run so that the
subsequent report can compare current PnL against the previous period.

Key layout::

    portfolio:snapshot:weekly:{YYYY-MM-DD}
    portfolio:snapshot:monthly:{YYYY-MM}

Values are JSON serialisations of :class:`PortfolioSnapshot` with the timestamp
in ISO 8601 (Asia/Taipei aware).  Entries expire automatically after 120 days.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapistock.cache import redis_cache

logger = logging.getLogger(__name__)

_SNAPSHOT_TTL_SECONDS: int = 120 * 24 * 3600
_WEEKLY_PREFIX: str = 'portfolio:snapshot:weekly'
_MONTHLY_PREFIX: str = 'portfolio:snapshot:monthly'
_TZ: ZoneInfo = ZoneInfo('Asia/Taipei')


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Immutable snapshot of the portfolio's total unrealized PnL.

    Attributes:
        pnl_tw: TW portfolio total unrealized PnL in TWD.
        pnl_us: US portfolio total unrealized PnL in USD.
        timestamp: Asia/Taipei aware timestamp when the snapshot was taken.
    """

    pnl_tw: float
    pnl_us: float
    timestamp: datetime


def _snapshot_to_dict(snapshot: PortfolioSnapshot) -> dict[str, object]:
    """Serialise a PortfolioSnapshot to a JSON-safe dict."""
    return {
        'pnl_tw': snapshot.pnl_tw,
        'pnl_us': snapshot.pnl_us,
        'timestamp': snapshot.timestamp.isoformat(),
    }


def _dict_to_snapshot(data: dict[str, object]) -> PortfolioSnapshot | None:
    """Deserialise a cached dict into a PortfolioSnapshot, None on malformed input."""
    try:
        ts_raw = str(data['timestamp'])
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_TZ)
        return PortfolioSnapshot(
            pnl_tw=float(data['pnl_tw']),  # type: ignore[arg-type]
            pnl_us=float(data['pnl_us']),  # type: ignore[arg-type]
            timestamp=ts,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning('Malformed portfolio snapshot: %s', exc)
        return None


def _save(key: str, snapshot: PortfolioSnapshot) -> None:
    """Persist a snapshot under *key* with the standard TTL."""
    try:
        redis_cache.put(key, _snapshot_to_dict(snapshot), _SNAPSHOT_TTL_SECONDS)
        logger.info('Portfolio snapshot saved: %s', key)
    except Exception as exc:
        logger.warning('Failed to save portfolio snapshot %s: %s', key, exc)


def _load(key: str) -> PortfolioSnapshot | None:
    """Read a snapshot at *key*; return None on miss, malformed data, or error."""
    try:
        raw = redis_cache.get(key)
    except Exception as exc:
        logger.warning('Failed to read portfolio snapshot %s: %s', key, exc)
        return None
    if raw is None:
        return None
    return _dict_to_snapshot(raw)


def save_weekly(snapshot: PortfolioSnapshot) -> None:
    """Persist a weekly snapshot keyed by the snapshot date (YYYY-MM-DD).

    Args:
        snapshot: Snapshot whose ``timestamp.date()`` becomes the key suffix.
    """
    iso_date = snapshot.timestamp.date().isoformat()
    _save(f'{_WEEKLY_PREFIX}:{iso_date}', snapshot)


def save_monthly(snapshot: PortfolioSnapshot) -> None:
    """Persist a monthly snapshot keyed by YYYY-MM of the snapshot's timestamp.

    Args:
        snapshot: Snapshot whose ``timestamp`` year/month become the key suffix.
    """
    year_month = snapshot.timestamp.strftime('%Y-%m')
    _save(f'{_MONTHLY_PREFIX}:{year_month}', snapshot)


def get_weekly(iso_date: str) -> PortfolioSnapshot | None:
    """Read the weekly snapshot for *iso_date* (YYYY-MM-DD).

    Args:
        iso_date: ISO 8601 date string identifying the snapshot.

    Returns:
        PortfolioSnapshot when present and valid, otherwise None.
    """
    return _load(f'{_WEEKLY_PREFIX}:{iso_date}')


def get_monthly(year_month: str) -> PortfolioSnapshot | None:
    """Read the monthly snapshot for *year_month* (YYYY-MM).

    Args:
        year_month: ``YYYY-MM`` string identifying the snapshot.

    Returns:
        PortfolioSnapshot when present and valid, otherwise None.
    """
    return _load(f'{_MONTHLY_PREFIX}:{year_month}')
