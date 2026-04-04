"""Shared rate-limiter instance backed by Redis.

A single ``Limiter`` is created here so that both the application factory
(main.py) and every router import the same storage backend.  Rate-limiting
is keyed by client IP via ``get_remote_address``.

``swallow_errors=True`` ensures graceful degradation: if Redis is
temporarily unavailable, requests are allowed through rather than
returning 500 errors.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapistock.config import redis_url

limiter: Limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=redis_url(),
    swallow_errors=True,
)
