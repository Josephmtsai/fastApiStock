"""Shared rate-limiter instance backed by Redis.

A single ``Limiter`` is created here so that both the application factory
(main.py) and every router import the same storage backend.  Rate-limiting
is keyed by client IP via ``get_remote_address``.

``swallow_errors=True`` ensures graceful degradation: if Redis is
temporarily unavailable, requests are allowed through rather than
returning 500 errors.

Set ``RATE_LIMIT_STORAGE_URI=memory://`` to use in-memory storage (tests).
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapistock.config import redis_url

# Allow tests (or environments without Redis) to override storage via env var.
_storage_uri: str = os.getenv('RATE_LIMIT_STORAGE_URI') or redis_url()

limiter: Limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
    swallow_errors=True,
)
