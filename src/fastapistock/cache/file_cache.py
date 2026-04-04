"""File-based JSON cache with TTL for stock data."""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_ROOT = Path('cache')


def _path(key: str) -> Path:
    """Resolve the file path for a cache key.

    Args:
        key: Cache key (e.g. '0050/2026-04-03').

    Returns:
        Absolute Path object for the cache file.
    """
    return _CACHE_ROOT / f'{key}.json'


def get(key: str, ttl: int) -> dict[str, object] | None:
    """Return cached value if it exists and has not expired.

    Args:
        key: Cache key used when the entry was stored.
        ttl: Maximum age in seconds before the entry is considered stale.

    Returns:
        The cached dict, or None if missing or expired.
    """
    cache_file = _path(key)
    if not cache_file.exists():
        return None

    try:
        raw = cache_file.read_text(encoding='utf-8')
        entry: dict[str, object] = json.loads(raw)
        stored_at = float(entry.get('_stored_at', 0))  # type: ignore[arg-type]
        if time.time() - stored_at > ttl:
            logger.debug('Cache expired for key=%s', key)
            return None
        value = entry.get('value')
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning('Cache read failed for key=%s: %s', key, exc)
        return None


def put(key: str, value: dict[str, object]) -> None:
    """Write a value to the file cache, creating parent dirs as needed.

    Args:
        key: Cache key (e.g. '0050/2026-04-03').
        value: Serialisable dict to store.
    """
    cache_file = _path(key)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {'_stored_at': time.time(), 'value': value}
    try:
        cache_file.write_text(json.dumps(entry), encoding='utf-8')
    except OSError as exc:
        logger.warning('Cache write failed for key=%s: %s', key, exc)


def invalidate(key: str) -> None:
    """Remove a cache entry if it exists.

    Args:
        key: Cache key to remove.
    """
    cache_file = _path(key)
    try:
        cache_file.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning('Cache invalidate failed for key=%s: %s', key, exc)
