"""Shared pytest fixtures for the fastapistock test suite."""

import fakeredis
import pytest


@pytest.fixture(autouse=True)
def _fake_redis_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Redis cache client with an in-memory fakeredis instance.

    This fixture runs automatically for every test, ensuring no test
    ever touches a real Redis server.  Each test gets a fresh
    ``FakeRedis`` instance so cache state does not leak between tests.
    """
    import fastapistock.cache.redis_cache as rc

    monkeypatch.setattr(rc, '_client', fakeredis.FakeRedis(decode_responses=True))
