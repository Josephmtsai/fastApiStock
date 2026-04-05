"""Shared pytest fixtures for the fastapistock test suite."""

import os

import fakeredis
import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Set env vars before any app modules are imported.

    ``RATE_LIMIT_STORAGE_URI=memory://`` ensures the slowapi rate-limiter
    uses in-memory storage during tests, avoiding Redis connection errors
    that cause ``AttributeError: 'State' object has no attribute
    'view_rate_limit'`` when Redis is unavailable.
    """
    os.environ.setdefault('RATE_LIMIT_STORAGE_URI', 'memory://')


@pytest.fixture(autouse=True)
def _fake_redis_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Redis cache client with an in-memory fakeredis instance.

    This fixture runs automatically for every test, ensuring no test
    ever touches a real Redis server.  Each test gets a fresh
    ``FakeRedis`` instance so cache state does not leak between tests.
    """
    import fastapistock.cache.redis_cache as rc

    monkeypatch.setattr(rc, '_client', fakeredis.FakeRedis(decode_responses=True))
