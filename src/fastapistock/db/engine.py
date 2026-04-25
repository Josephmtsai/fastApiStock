"""SQLAlchemy engine and session factory for Postgres persistence.

The engine is lazily constructed on first use so unit tests that do not
touch the database never need a live ``DATABASE_URL``.
"""

from __future__ import annotations

import logging
from threading import Lock

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from fastapistock.config import DATABASE_URL

_logger = logging.getLogger('fastapistock.report_history')

_POOL_SIZE = 5
_MAX_OVERFLOW = 10

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_lock = Lock()


def _build_engine(url: str) -> Engine:
    """Create a configured SQLAlchemy engine.

    Args:
        url: Postgres connection string (sqlalchemy-compatible).

    Returns:
        Engine with connection pool tuned for a small FastAPI deployment.
    """
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
        future=True,
    )


def _init() -> tuple[Engine, sessionmaker[Session]]:
    """Initialise the singleton engine and session factory.

    Returns:
        Tuple of (engine, session factory).

    Raises:
        RuntimeError: If ``DATABASE_URL`` is not configured.
    """
    global _engine, _session_factory
    if _engine is not None and _session_factory is not None:
        return _engine, _session_factory
    with _lock:
        if _engine is not None and _session_factory is not None:
            return _engine, _session_factory
        if not DATABASE_URL:
            raise RuntimeError(
                'DATABASE_URL is not configured; cannot create SQLAlchemy engine'
            )
        _engine = _build_engine(DATABASE_URL)
        _session_factory = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, future=True
        )
        _logger.info('report_history.db.engine.created')
        return _engine, _session_factory


def get_engine() -> Engine:
    """Return the lazily-initialised singleton engine.

    Returns:
        SQLAlchemy ``Engine`` bound to ``DATABASE_URL``.

    Raises:
        RuntimeError: If ``DATABASE_URL`` is not configured.
    """
    engine, _ = _init()
    return engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory bound to the shared engine.

    Returns:
        ``sessionmaker`` that produces new ``Session`` instances per call.
    """
    _, factory = _init()
    return factory


def SessionLocal() -> Session:
    """Return a new SQLAlchemy session bound to the shared engine.

    Named ``SessionLocal`` to match the conventional SQLAlchemy factory alias
    while remaining a plain callable (avoids shadowing the class name).

    Returns:
        A new ``Session`` the caller is responsible for closing.
    """
    return get_session_factory()()
