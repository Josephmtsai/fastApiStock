"""Structured request/response/performance logging middleware.

Emits three log lines per request:

  REQ  {DateTime} {pid} {method_name} {client_ip} {http_method} REQ {request_data}
  RES  {DateTime} {pid} {method_name} {client_ip} {http_method} RES {status} {body}
  PERF {DateTime} {pid} {method_name} PERF {elapsed_ms}ms

Log level follows HTTP status: 2xx → INFO, 4xx → WARNING, 5xx → ERROR.
PERF is always INFO.
"""

import logging
import os
import re
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_logger = logging.getLogger(__name__)

_PID: int = os.getpid()
_MAX_BODY: int = 500
_SENSITIVE: re.Pattern[str] = re.compile(
    r'(password|token|secret|authorization|passwd|pwd)([=:]\s*)([^\s&,;"\']+)',
    re.IGNORECASE,
)


def _client_ip(request: Request) -> str:
    """Extract the real client IP, preferring X-Forwarded-For.

    Args:
        request: Incoming HTTP request.

    Returns:
        IP address string.
    """
    forwarded: str | None = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return str(request.client.host) if request.client else 'unknown'


def _mask_sensitive(text: str) -> str:
    """Replace values of sensitive keys with ``***``.

    Args:
        text: Serialised request/response string to sanitise.

    Returns:
        String with sensitive values masked.
    """
    return _SENSITIVE.sub(r'\1\2***', text)


def _route_name(request: Request) -> str:
    """Derive a short method name from the matched route or path.

    Args:
        request: Incoming HTTP request (may have a route after routing).

    Returns:
        Route operation ID or the raw path.
    """
    route = request.scope.get('route')
    if route and hasattr(route, 'name'):
        return str(route.name)
    return str(request.url.path)


def _request_data(request: Request) -> str:
    """Serialise path params and query params for logging.

    Args:
        request: Incoming HTTP request.

    Returns:
        Masked, single-line summary of request parameters.
    """
    parts: list[str] = []
    path_params = request.path_params
    if path_params:
        parts.append(f'path={dict(path_params)}')
    query = str(request.query_params)
    if query:
        parts.append(f'query={query}')
    raw = ' '.join(parts) if parts else '-'
    return _mask_sensitive(raw)


def _truncate(body: bytes) -> str:
    """Decode and truncate *body* to ``_MAX_BODY`` characters.

    Args:
        body: Raw response body bytes.

    Returns:
        UTF-8 decoded string, truncated with ``…`` if over limit.
    """
    text = body.decode('utf-8', errors='replace')
    if len(text) > _MAX_BODY:
        return text[:_MAX_BODY] + '…'
    return text


def _level(status: int) -> int:
    """Map HTTP status code to Python logging level.

    Args:
        status: HTTP response status code.

    Returns:
        ``logging.INFO``, ``logging.WARNING``, or ``logging.ERROR``.
    """
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO


class LoggingMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """Emit REQ / RES / PERF log lines for every request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Log request, invoke handler, then log response and timing.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            The unmodified response from the handler.
        """
        ip = _client_ip(request)
        method = request.method
        req_data = _request_data(request)

        _logger.info(
            '%d %s %s %s REQ %s',
            _PID,
            _route_name(request),
            ip,
            method,
            req_data,
        )

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Buffer the body so we can log it without consuming the stream.
        body = b''
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        status = response.status_code
        res_text = _mask_sensitive(_truncate(body))

        _logger.log(
            _level(status),
            '%d %s %s %s RES %d %s',
            _PID,
            _route_name(request),
            ip,
            method,
            status,
            res_text,
        )
        _logger.info('%d %s PERF %dms', _PID, _route_name(request), elapsed_ms)

        # Rebuild the response with the buffered body.
        return Response(
            content=body,
            status_code=status,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
