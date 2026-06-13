"""Foreign exchange service: USD/TWD spot rate via yfinance + Redis cache."""

from __future__ import annotations

import logging
import random
import time
from datetime import date

import yfinance

from fastapistock.cache import redis_cache
from fastapistock.config import FX_CACHE_TTL, YFINANCE_TIMEOUT

logger = logging.getLogger(__name__)

_FX_TICKER = 'TWD=X'


def _cache_key() -> str:
    """Return today's Redis cache key for the USD/TWD rate.

    Returns:
        Cache key string scoped to the current calendar date,
        e.g. ``'fx:usd_twd:2026-06-13'``.
    """
    return f'fx:usd_twd:{date.today().isoformat()}'


def _fetch_live_rate() -> float | None:
    """Fetch the current USD/TWD rate from yfinance with a random delay.

    Applies a brief random sleep before the network call per CLAUDE.md external
    API policy, then retrieves the last Close value from a 1-day history window.

    Returns:
        Rate as a float (e.g. ``32.5``), or ``None`` if the fetch fails
        or returns an empty result.
    """
    try:
        time.sleep(random.uniform(0.1, 0.4))  # noqa: S311 — jitter delay, not cryptographic
        ticker = yfinance.Ticker(_FX_TICKER)
        hist = ticker.history(period='1d', timeout=YFINANCE_TIMEOUT)
        if hist.empty:
            logger.warning('FX fetch returned empty DataFrame for %s', _FX_TICKER)
            return None
        rate: float = float(hist['Close'].iloc[-1])
        return rate
    except Exception:
        logger.warning('FX fetch failed for %s', _FX_TICKER, exc_info=True)
        return None


def get_usd_twd_rate() -> float | None:
    """Return today's USD/TWD spot rate, Redis-cached.

    Checks Redis for a cached value keyed to the current calendar date.
    On a cache miss, calls yfinance and writes the result back to Redis
    with TTL ``FX_CACHE_TTL``.  Any failure is swallowed and ``None``
    is returned so callers can fall back gracefully.

    Returns:
        Rate as float (e.g. ``32.50``), or ``None`` if unavailable.
    """
    key = _cache_key()
    cached = redis_cache.get(key)
    if cached is not None:
        try:
            raw_rate = cached['rate']
            if not isinstance(raw_rate, (int, float)):
                raise TypeError(f'Expected numeric rate, got {type(raw_rate).__name__}')
            return float(raw_rate)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning('FX cache entry malformed for key=%s: %s', key, exc)

    rate = _fetch_live_rate()
    if rate is not None:
        redis_cache.put(key, {'rate': rate}, ttl=FX_CACHE_TTL)
    return rate
