"""Shared pytest fixtures for the fastapistock test suite."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import fakeredis
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.compiler import TypeCompiler


@compiles(BigInteger, 'sqlite')  # type: ignore[misc, no-untyped-call]
def _sqlite_bigint_as_integer(
    type_: BigInteger, compiler: TypeCompiler, **kw: Any
) -> str:
    """Render ``BigInteger`` as ``INTEGER`` for SQLite so rowid autoincrement works.

    SQLite's autoincrement is only triggered by the literal ``INTEGER PRIMARY
    KEY`` declaration; ``BIGINT`` becomes a separate type that does not get
    a rowid alias.  This compiler override is test-only (Postgres production
    DDL is unaffected) and lets the in-memory engine accept inserts that
    omit the ``id`` column.
    """
    return 'INTEGER'


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


@pytest.fixture
def db_session(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Session, None, None]:
    """Yield a SQLite in-memory session isolated from production singletons.

    The fixture builds a fresh in-memory engine per test, creates all spec-006
    tables on it, and patches ``fastapistock.db.engine`` so any repository
    code under test reuses this engine via ``SessionLocal()``.  Both the
    private singleton (``_engine``/``_session_factory``) and the public
    ``get_engine``/``get_session_factory`` helpers are overridden so a
    previously-initialised production engine cannot leak in.
    """
    import fastapistock.db.engine as db_engine
    from fastapistock.db.models import Base

    engine = create_engine(
        'sqlite+pysqlite:///:memory:',
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # Patching the singleton state is enough: ``SessionLocal`` reads these
    # module-level globals at call time via ``_init()``.  We don't need to
    # override the function symbol itself.
    monkeypatch.setattr(db_engine, '_engine', engine)
    monkeypatch.setattr(db_engine, '_session_factory', factory)

    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
