"""FastAPI application factory.

This module only creates the app, registers routers, and configures
middleware and exception handlers. Zero business logic lives here.
"""

import logging
import logging.config
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from fastapistock.exceptions import register_exception_handlers
from fastapistock.middleware.logging import LoggingMiddleware
from fastapistock.middleware.rate_limit import get_limiter
from fastapistock.routers import health, index, stocks, telegram

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


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance ready to serve requests.
    """
    application = FastAPI(title='FastAPI Stock', version='0.1.0')

    # Middleware order: outermost first (LoggingMiddleware wraps everything).
    application.add_middleware(LoggingMiddleware)
    application.add_middleware(_RateLimitMiddleware)

    register_exception_handlers(application)

    application.include_router(index.router)
    application.include_router(health.router)
    application.include_router(stocks.router)
    application.include_router(telegram.router)

    return application


app = create_app()
