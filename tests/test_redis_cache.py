"""Unit tests for the Redis cache module."""

import json

import fakeredis

import fastapistock.cache.redis_cache as rc


def _make_fake() -> fakeredis.FakeRedis:  # type: ignore[type-arg]
    """Return a fresh FakeRedis instance with decode_responses=True."""
    return fakeredis.FakeRedis(decode_responses=True)


class TestGet:
    def test_returns_none_on_cache_miss(self, monkeypatch: object) -> None:
        monkeypatch.setattr(rc, '_client', _make_fake())  # type: ignore[attr-defined]
        assert rc.get('missing-key') is None

    def test_returns_dict_after_put(self, monkeypatch: object) -> None:
        monkeypatch.setattr(rc, '_client', _make_fake())  # type: ignore[attr-defined]
        rc.put('k', {'x': 1}, ttl=60)
        result = rc.get('k')
        assert result == {'x': 1}

    def test_returns_none_after_ttl_expired(self, monkeypatch: object) -> None:
        fake = _make_fake()
        monkeypatch.setattr(rc, '_client', fake)  # type: ignore[attr-defined]
        rc.put('k', {'v': 'data'}, ttl=1)
        # Simulate expiry by deleting the key directly
        fake.delete('k')
        assert rc.get('k') is None

    def test_returns_none_on_invalid_json(self, monkeypatch: object) -> None:
        fake = _make_fake()
        monkeypatch.setattr(rc, '_client', fake)  # type: ignore[attr-defined]
        fake.set('bad', 'not-json')
        assert rc.get('bad') is None


class TestPut:
    def test_value_stored_with_ttl(self, monkeypatch: object) -> None:
        fake = _make_fake()
        monkeypatch.setattr(rc, '_client', fake)  # type: ignore[attr-defined]
        rc.put('k', {'a': 'b'}, ttl=300)
        raw: str | None = fake.get('k')  # type: ignore[assignment]
        assert raw is not None
        assert json.loads(raw) == {'a': 'b'}
        ttl: int = fake.ttl('k')  # type: ignore[assignment]
        assert 0 < ttl <= 300

    def test_put_overwrites_existing(self, monkeypatch: object) -> None:
        fake = _make_fake()
        monkeypatch.setattr(rc, '_client', fake)  # type: ignore[attr-defined]
        rc.put('k', {'v': 1}, ttl=60)
        rc.put('k', {'v': 2}, ttl=60)
        assert rc.get('k') == {'v': 2}


class TestInvalidate:
    def test_invalidate_removes_key(self, monkeypatch: object) -> None:
        fake = _make_fake()
        monkeypatch.setattr(rc, '_client', fake)  # type: ignore[attr-defined]
        rc.put('k', {'x': 1}, ttl=60)
        rc.invalidate('k')
        assert rc.get('k') is None

    def test_invalidate_missing_key_is_noop(self, monkeypatch: object) -> None:
        monkeypatch.setattr(rc, '_client', _make_fake())  # type: ignore[attr-defined]
        rc.invalidate('never-set')  # must not raise
