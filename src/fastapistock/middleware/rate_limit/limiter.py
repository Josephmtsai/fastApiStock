"""Redis sliding-window rate limiter implementation.

Uses two Redis keys per (ip, route-group):
  ``ratelimit:{prefix}:{ip}``        Sorted Set — uuid members, ms timestamps as scores
  ``ratelimit:{prefix}:{ip}:locked`` String     — value=ip, TTL=block_seconds
"""

import logging
import time
import uuid

import redis

from fastapistock.config import redis_url
from fastapistock.middleware.rate_limit.config import RateLimitConfig

_logger = logging.getLogger(__name__)

_client: redis.Redis | None = None  # type: ignore[type-arg]


def _get_client() -> redis.Redis:  # type: ignore[type-arg]
    """Return the shared Redis client, creating it on first call.

    Returns:
        ``redis.Redis`` with short socket timeouts (fail fast, not hang).
    """
    global _client
    if _client is None:
        _client = redis.from_url(
            redis_url(),
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
        )
    return _client


class RateLimiter:
    """Sliding-window IP rate limiter backed by Redis sorted sets.

    Each instance operates on its own key namespace (``key_prefix``)
    so different route groups don't share counters.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        """Initialise a limiter for one route group.

        Args:
            config: Window, limit, block duration and key prefix settings.
        """
        self._config = config

    def is_rate_limited(self, ip: str) -> bool:
        """Check and record a request for *ip*.

        Steps:
          1. Return True immediately if the block key exists (O(1)).
          2. Add request to the sorted set, prune old entries, count.
          3. If count >= limit → write block key, return True.

        Args:
            ip: Client IP address string.

        Returns:
            True  → caller should respond with HTTP 429.
            False → request is within limits (or Redis is unavailable).
        """
        try:
            client = _get_client()
            cfg = self._config
            rate_key = f'ratelimit:{cfg.key_prefix}:{ip}'
            block_key = f'ratelimit:{cfg.key_prefix}:{ip}:locked'

            # Step 1 — block key (O(1))
            if client.exists(block_key):
                _logger.info('Blocked ip=%s prefix=%s', ip, cfg.key_prefix)
                return True

            # Step 2 — sliding window
            now_ms = int(time.time() * 1000)
            window_start_ms = now_ms - cfg.window_seconds * 1000
            member = str(uuid.uuid4())

            pipe = client.pipeline()
            pipe.zadd(rate_key, {member: now_ms})
            pipe.zremrangebyscore(rate_key, 0, window_start_ms)
            pipe.zcard(rate_key)
            pipe.expire(rate_key, cfg.window_seconds + 1)
            results = pipe.execute()

            count: int = results[2]

            # Step 3 — trigger block
            if count >= cfg.limit:
                client.set(block_key, ip, ex=cfg.block_seconds)
                _logger.warning(
                    'Rate limit exceeded prefix=%s ip=%s count=%d — blocked %ds',
                    cfg.key_prefix,
                    ip,
                    count,
                    cfg.block_seconds,
                )
                return True

            return False

        except Exception as exc:
            _logger.warning(
                'Rate limit error prefix=%s ip=%s: %s — allowing',
                self._config.key_prefix,
                ip,
                exc,
            )
            return False  # fail-open on Redis error
