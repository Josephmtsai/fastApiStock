"""Custom exception handlers that return the standard ResponseEnvelope."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fastapistock.repositories.twstock_repo import StockNotFoundError

logger = logging.getLogger(__name__)


async def _stock_not_found_handler(
    _request: Request,
    exc: StockNotFoundError,
) -> JSONResponse:
    """Return a 404 envelope for unknown stock symbols.

    Args:
        _request: Incoming HTTP request (unused).
        exc: The StockNotFoundError raised by the service layer.

    Returns:
        JSONResponse with status 404 and error envelope.
    """
    return JSONResponse(
        status_code=404,
        content={'status': 'error', 'data': None, 'message': str(exc)},
    )


async def _validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Override FastAPI's default 422 handler to use the ResponseEnvelope.

    Args:
        _request: Incoming HTTP request (unused).
        exc: Pydantic validation error from request parsing.

    Returns:
        JSONResponse with status 422 and error envelope.
    """
    first_error = exc.errors()[0] if exc.errors() else {}
    message = first_error.get('msg', 'Validation error')
    return JSONResponse(
        status_code=422,
        content={'status': 'error', 'data': None, 'message': str(message)},
    )


async def _generic_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all 500 handler that returns the ResponseEnvelope.

    Args:
        _request: Incoming HTTP request (unused).
        exc: Any unhandled exception.

    Returns:
        JSONResponse with status 500 and error envelope.
    """
    logger.exception('Unhandled exception: %s', exc)
    return JSONResponse(
        status_code=500,
        content={'status': 'error', 'data': None, 'message': 'Internal server error'},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(StockNotFoundError, _stock_not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _generic_exception_handler)
