"""Root index router — lists all available API endpoints."""

from fastapi import APIRouter, Request

from fastapistock.schemas.common import ResponseEnvelope

router = APIRouter(tags=['index'])


@router.get(
    '/',
    response_model=ResponseEnvelope[list[dict[str, str]]],
    summary='API index — list all available endpoints',
)
async def api_index(request: Request) -> ResponseEnvelope[list[dict[str, str]]]:
    """Return a summary of every registered API route.

    Args:
        request: FastAPI request (used to introspect ``app.routes``).

    Returns:
        ResponseEnvelope whose data is a list of
        ``{method, path, summary}`` dicts for each non-internal route.
    """
    routes: list[dict[str, str]] = []
    for route in request.app.routes:
        if not hasattr(route, 'methods'):
            continue
        path: str = getattr(route, 'path', '')
        summary: str = getattr(route, 'summary', '') or getattr(route, 'name', '')
        for http_method in sorted(route.methods or []):
            routes.append({'method': http_method, 'path': path, 'summary': summary})
    return ResponseEnvelope(status='success', data=routes)
