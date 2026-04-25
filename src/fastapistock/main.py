"""FastAPI application factory.

This module only creates the app, registers routers, and configures
middleware and exception handlers. Zero business logic lives here.
"""

import logging
import logging.config
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from fastapistock.config import DATABASE_URL, TELEGRAM_TOKEN
from fastapistock.exceptions import register_exception_handlers
from fastapistock.middleware.logging import LoggingMiddleware
from fastapistock.middleware.rate_limit import get_limiter
from fastapistock.routers import (
    health,
    index,
    reports,
    stocks,
    telegram,
    us_telegram,
    webhook,
)
from fastapistock.scheduler import build_scheduler

_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
}

logging.config.dictConfig(_LOGGING_CONFIG)
_logger = logging.getLogger(__name__)

_RATE_LIMIT_EXEMPT = {'/health'}

_BOT_COMMANDS = [
    {'command': 'q', 'description': '本季投資達成率'},
    {'command': 'us', 'description': '美股報價，例：/us AAPL,TSLA'},
    {'command': 'tw', 'description': '台股報價，例：/tw 0050,2330'},
    {'command': 'help', 'description': '顯示所有指令說明'},
]


def _register_bot_commands() -> None:
    """Register the bot command menu with Telegram via setMyCommands.

    This is an idempotent startup call. Errors are logged but never fatal.
    """
    if not TELEGRAM_TOKEN:
        _logger.warning('TELEGRAM_TOKEN not set — skipping setMyCommands')
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands'
    try:
        resp = httpx.post(url, json={'commands': _BOT_COMMANDS}, timeout=10)
        resp.raise_for_status()
        _logger.info('Telegram bot commands registered successfully')
    except Exception as exc:  # network errors are non-fatal at startup
        _logger.warning('Failed to register Telegram bot commands: %s', exc)


def _verify_database_connection() -> None:
    """Probe the configured Postgres database at application startup.

    Logs a structured ok / fail event under the
    ``fastapistock.report_history`` namespace. Failure is non-fatal so a
    transient DB outage cannot prevent the rest of the service from
    starting (the report history feature degrades, other endpoints stay
    up).
    """
    history_logger = logging.getLogger('fastapistock.report_history')
    if not DATABASE_URL:
        history_logger.warning(
            'report_history.db.startup.skipped: DATABASE_URL not configured'
        )
        return
    try:
        from fastapistock.db import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            conn.exec_driver_sql('SELECT 1')
        history_logger.info('report_history.db.startup.ok')
    except Exception as exc:
        history_logger.error(
            'report_history.db.startup.fail: %s: %s',
            type(exc).__name__,
            exc,
            exc_info=True,
        )


class _RateLimitMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """Middleware that applies per-route sliding-window rate limiting.

    Routes in ``_RATE_LIMIT_EXEMPT`` are skipped.  All others are
    matched to the most-specific ``RateLimiter`` via ``get_limiter()``.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Intercept each request and enforce the rate limit.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            429 JSONResponse if rate-limited, otherwise the normal response.
        """
        if request.url.path not in _RATE_LIMIT_EXEMPT:
            ip = request.client.host if request.client else 'unknown'
            limiter = get_limiter(request.url.path)
            if limiter.is_rate_limited(ip):
                cfg = limiter._config
                return JSONResponse(
                    status_code=429,
                    content={
                        'status': 'error',
                        'data': None,
                        'message': (
                            f'Too many requests. '
                            f'Blocked for {cfg.block_seconds} seconds.'
                        ),
                    },
                )
        return await call_next(request)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage APScheduler lifecycle tied to the FastAPI application.

    Starts the scheduler on application startup and shuts it down cleanly
    on application shutdown, regardless of how the shutdown is triggered.

    Args:
        app: The FastAPI application instance (unused but required by protocol).

    Yields:
        Control to the running application.
    """
    scheduler = build_scheduler()
    scheduler.start()
    _logger.info('APScheduler started')
    _register_bot_commands()
    _verify_database_connection()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        _logger.info('APScheduler stopped')


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance ready to serve requests.
    """
    application = FastAPI(title='FastAPI Stock', version='0.1.0', lifespan=_lifespan)

    # Middleware order: outermost first (LoggingMiddleware wraps everything).
    application.add_middleware(LoggingMiddleware)
    application.add_middleware(_RateLimitMiddleware)

    register_exception_handlers(application)

    application.include_router(index.router)
    application.include_router(health.router)
    application.include_router(stocks.router)
    application.include_router(telegram.router)
    application.include_router(us_telegram.router)
    application.include_router(webhook.router)
    application.include_router(reports.router)

    return application


app = create_app()
