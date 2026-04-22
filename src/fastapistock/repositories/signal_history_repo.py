"""Repository for persisting cost-level signal history in Redis.

Signals are written every time a qualifying drawdown + MA50 breach is detected
(see :func:`fastapistock.services.telegram_service._calc_cost_signal`).  Each
record is stored under a deterministic key so re-triggers within the same day
and tier are deduplicated but tier upgrades produce additional entries.

Key layout::

    signal:history:{market}:{symbol}:{YYYY-MM-DD}:{tier}

Value is the JSON serialisation of :class:`SignalRecord` (timestamp as ISO
8601).  Entries expire automatically after 120 days.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast
from zoneinfo import ZoneInfo

import redis

from fastapistock.cache import redis_cache

logger = logging.getLogger(__name__)

_SIGNAL_TTL_SECONDS: int = 120 * 24 * 3600
_KEY_PREFIX: str = 'signal:history'
_SCAN_MATCH: str = f'{_KEY_PREFIX}:*'
_SCAN_COUNT: int = 500
_TZ: ZoneInfo = ZoneInfo('Asia/Taipei')


@dataclass(frozen=True)
class SignalRecord:
    """Immutable cost-level signal event.

    Attributes:
        symbol: Stock symbol (TW numeric code or US ticker).
        market: 'TW' or 'US'.
        tier: 1, 2, or 3 (maps to one/two/three-star severity).
        drop_pct: Percent drawdown vs. 52-week high (negative number).
        price: Stock price at the time of signal.
        week52_high: 52-week high used to derive drop_pct.
        ma50: 50-day moving average (price is below this at signal time).
        timestamp: Asia/Taipei aware timestamp when signal was detected.
    """

    symbol: str
    market: str
    tier: int
    drop_pct: float
    price: float
    week52_high: float
    ma50: float
    timestamp: datetime


def _build_key(record: SignalRecord) -> str:
    """Construct the Redis key for a signal record."""
    iso_date = record.timestamp.date().isoformat()
    return f'{_KEY_PREFIX}:{record.market}:{record.symbol}:{iso_date}:{record.tier}'


def _record_to_dict(record: SignalRecord) -> dict[str, object]:
    """Serialise a SignalRecord to a JSON-safe dict."""
    return {
        'symbol': record.symbol,
        'market': record.market,
        'tier': record.tier,
        'drop_pct': record.drop_pct,
        'price': record.price,
        'week52_high': record.week52_high,
        'ma50': record.ma50,
        'timestamp': record.timestamp.isoformat(),
    }


def _dict_to_record(data: dict[str, object]) -> SignalRecord | None:
    """Deserialise a cached dict into a SignalRecord, or None on malformed input."""
    try:
        ts_raw = str(data['timestamp'])
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_TZ)
        return SignalRecord(
            symbol=str(data['symbol']),
            market=str(data['market']),
            tier=int(cast(float, data['tier'])),
            drop_pct=float(cast(float, data['drop_pct'])),
            price=float(cast(float, data['price'])),
            week52_high=float(cast(float, data['week52_high'])),
            ma50=float(cast(float, data['ma50'])),
            timestamp=ts,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning('Malformed signal record: %s', exc)
        return None


def save_signal(record: SignalRecord) -> None:
    """Persist a signal record to Redis with a 120-day TTL.

    Redis errors are swallowed with a warning log so signal detection never
    propagates failures to the push pipeline.

    Args:
        record: The SignalRecord to persist.
    """
    key = _build_key(record)
    try:
        redis_cache.put(key, _record_to_dict(record), _SIGNAL_TTL_SECONDS)
        logger.info('Signal saved: %s', key)
    except Exception as exc:  # redis errors already logged by redis_cache
        logger.warning('Failed to save signal %s: %s', key, exc)


def _parse_key_date(key: str) -> date | None:
    """Extract the date component from a signal history key.

    Args:
        key: Full Redis key, e.g. 'signal:history:TW:2330:2026-04-22:2'.

    Returns:
        Parsed date, or None when the key doesn't conform to the expected shape.
    """
    parts = key.split(':')
    # expected: ['signal', 'history', market, symbol, YYYY-MM-DD, tier]
    if len(parts) != 6:
        return None
    try:
        return date.fromisoformat(parts[4])
    except ValueError:
        return None


def list_signals(start_date: date, end_date: date) -> list[SignalRecord]:
    """Return all signal records whose key-date falls within [start_date, end_date].

    Uses ``SCAN`` (never ``KEYS``) to avoid blocking Redis. Malformed keys or
    values are skipped with a warning. Any Redis-level failure results in an
    empty list and a warning log.

    Args:
        start_date: Inclusive lower bound of the date range.
        end_date: Inclusive upper bound of the date range.

    Returns:
        List of SignalRecord objects, unordered.
    """
    if end_date < start_date:
        return []

    try:
        client = redis_cache._get_client()
    except Exception as exc:
        logger.warning('Redis client unavailable for list_signals: %s', exc)
        return []

    matched_keys: list[str] = []
    try:
        cursor = 0
        while True:
            cursor, keys = client.scan(  # type: ignore[misc]
                cursor=cursor, match=_SCAN_MATCH, count=_SCAN_COUNT
            )
            for raw_key in keys:
                key = raw_key if isinstance(raw_key, str) else raw_key.decode('utf-8')
                key_date = _parse_key_date(key)
                if key_date is None:
                    continue
                if start_date <= key_date <= end_date:
                    matched_keys.append(key)
            if cursor == 0:
                break
    except redis.RedisError as exc:
        logger.warning('SCAN failed for signal history: %s', exc)
        return []
    except Exception as exc:
        logger.warning('Unexpected error listing signals: %s', exc)
        return []

    records: list[SignalRecord] = []
    for key in matched_keys:
        try:
            raw = cast(str | None, client.get(key))
        except redis.RedisError as exc:
            logger.warning('GET failed for %s: %s', key, exc)
            continue
        if raw is None:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning('Invalid JSON at %s: %s', key, exc)
            continue
        if not isinstance(payload, dict):
            continue
        record = _dict_to_record(payload)
        if record is not None:
            records.append(record)

    return records
