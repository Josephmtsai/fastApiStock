"""FastAPI application factory.

This module only creates the app, registers routers, and configures
middleware and exception handlers. Zero business logic lives here.
"""

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from fastapistock.exceptions import register_exception_handlers
from fastapistock.routers import health, stocks


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance ready to serve requests.
    """
    application = FastAPI(title='FastAPI Stock', version='0.1.0')

    limiter = Limiter(key_func=get_remote_address)
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    register_exception_handlers(application)

    application.include_router(health.router)
    application.include_router(stocks.router)

    return application


app = create_app()
