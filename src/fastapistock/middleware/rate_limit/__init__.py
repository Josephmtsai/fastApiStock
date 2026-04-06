"""Rate limit package.

Builds one ``RateLimiter`` per route group from env vars and exposes
``get_limiter(path)`` for the middleware to pick the right one.

Route → env prefix mapping:
    /api/v1/stock/*      → RATE_LIMIT_STOCK_*
    /api/v1/tgMessage/*  → RATE_LIMIT_TG_*
    everything else      → RATE_LIMIT_*   (default)
"""

from fastapistock.middleware.rate_limit.config import load_config
from fastapistock.middleware.rate_limit.limiter import RateLimiter

# One limiter instance per route group — built once at import time.
_limiters: dict[str, RateLimiter] = {
    '/api/v1/stock': RateLimiter(load_config('STOCK')),
    '/api/v1/tgMessage': RateLimiter(load_config('TG')),
}
_default_limiter = RateLimiter(load_config())


def get_limiter(path: str) -> RateLimiter:
    """Return the ``RateLimiter`` whose prefix matches *path*.

    Args:
        path: Request URL path (e.g. ``'/api/v1/stock/0050'``).

    Returns:
        The most-specific matching ``RateLimiter``, or the default one.
    """
    for prefix, limiter in _limiters.items():
        if path.startswith(prefix):
            return limiter
    return _default_limiter
