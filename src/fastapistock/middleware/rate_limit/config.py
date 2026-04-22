"""Rate limit configuration loaded from environment variables.

Each route group can have its own window/count/block settings via
prefixed env vars.  Falls back to the default (unprefixed) values.

Env var pattern:
    RATE_LIMIT_{PREFIX}_WINDOW   sliding window in seconds
    RATE_LIMIT_{PREFIX}_COUNT    max requests before block triggers
    RATE_LIMIT_{PREFIX}_BLOCK    block duration in seconds

Default (no prefix):
    RATE_LIMIT_WINDOW   (default 60)
    RATE_LIMIT_COUNT    (default 10)
    RATE_LIMIT_BLOCK    (default 600)

Example .env:
    RATE_LIMIT_WINDOW=60
    RATE_LIMIT_COUNT=10
    RATE_LIMIT_BLOCK=600
    RATE_LIMIT_STOCK_WINDOW=60
    RATE_LIMIT_STOCK_COUNT=60
    RATE_LIMIT_STOCK_BLOCK=600
    RATE_LIMIT_TG_WINDOW=60
    RATE_LIMIT_TG_COUNT=30
    RATE_LIMIT_TG_BLOCK=600
    RATE_LIMIT_REPORT_WINDOW=60
    RATE_LIMIT_REPORT_COUNT=10
    RATE_LIMIT_REPORT_BLOCK=600
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    """Immutable rate limit parameters for one route group.

    Attributes:
        window_seconds: Sliding window length in seconds.
        limit: Maximum requests allowed within the window before blocking.
        block_seconds: How long a blocked IP stays locked out.
        key_prefix: Redis key namespace (e.g. 'stock', 'tg', 'default').
    """

    window_seconds: int
    limit: int
    block_seconds: int
    key_prefix: str


def load_config(prefix: str = '') -> RateLimitConfig:
    """Build a ``RateLimitConfig`` from environment variables.

    Args:
        prefix: Optional route group name (e.g. 'STOCK', 'TG').
            When given, reads ``RATE_LIMIT_{PREFIX}_*`` vars and falls back
            to the unprefixed defaults.

    Returns:
        A populated ``RateLimitConfig`` instance.
    """
    env_prefix = f'RATE_LIMIT_{prefix}_' if prefix else 'RATE_LIMIT_'
    key_name = prefix.lower() if prefix else 'default'

    def _get(name: str, default: int) -> int:
        raw = os.getenv(f'{env_prefix}{name}') or os.getenv(f'RATE_LIMIT_{name}')
        return int(raw) if raw else default

    return RateLimitConfig(
        window_seconds=_get('WINDOW', 60),
        limit=_get('COUNT', 10),
        block_seconds=_get('BLOCK', 600),
        key_prefix=key_name,
    )
