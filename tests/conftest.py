"""Shared pytest fixtures for the fastapistock test suite."""

import fakeredis
import pytest


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace all Redis clients with in-memory fakeredis instances.

    Patches the stock cache client and the rate-limiter client so
    no test ever touches a real Redis server.  Each test gets fresh
    instances to prevent state leaking between tests.
    """
    import fastapistock.cache.redis_cache as rc
    import fastapistock.middleware.rate_limit.limiter as rl

    monkeypatch.setattr(rc, '_client', fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(rl, '_client', fakeredis.FakeRedis(decode_responses=True))
