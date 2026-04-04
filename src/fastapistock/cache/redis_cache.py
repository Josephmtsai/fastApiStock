"""Redis-backed cache for stock data with native TTL support.

The module holds a single lazy-initialised client.  Tests can replace
``_client`` via ``monkeypatch`` before the first request to inject a
``fakeredis.FakeRedis`` instance without touching real infrastructure.
"""

from __future__ import annotations

import json
import logging
from typing import cast

import redis

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None  # type: ignore[type-arg]


def _get_client() -> redis.Redis:  # type: ignore[type-arg]
    """Return the shared Redis client, creating it on first call.

    Returns:
        A ``redis.Redis`` instance configured with ``decode_responses=True``
        so all values are returned as strings rather than bytes.
    """
    global _client
    if _client is None:
        from fastapistock.config import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT

        _client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )
    return _client


def get(key: str) -> dict[str, object] | None:
    """Return the cached value for *key*, or ``None`` on miss or error.

    Args:
        key: Cache key (e.g. ``'stock:0050:2026-04-04'``).

    Returns:
        The cached dict, or ``None`` if the key is absent or Redis fails.
    """
    try:
        raw = cast(str | None, _get_client().get(key))
        if raw is None:
            return None
        result: dict[str, object] = json.loads(raw)
        return result
    except (redis.RedisError, json.JSONDecodeError) as exc:
        logger.warning('Cache get failed for key=%s: %s', key, exc)
        return None


def put(key: str, value: dict[str, object], ttl: int) -> None:
    """Store *value* under *key* with an expiry of *ttl* seconds.

    Args:
        key: Cache key.
        value: JSON-serialisable dict to store.
        ttl: Time-to-live in seconds; Redis evicts the key after this.
    """
    try:
        _get_client().setex(key, ttl, json.dumps(value))
    except redis.RedisError as exc:
        logger.warning('Cache put failed for key=%s: %s', key, exc)


def invalidate(key: str) -> None:
    """Delete *key* from the cache if it exists.

    Args:
        key: Cache key to remove.
    """
    try:
        _get_client().delete(key)
    except redis.RedisError as exc:
        logger.warning('Cache invalidate failed for key=%s: %s', key, exc)
