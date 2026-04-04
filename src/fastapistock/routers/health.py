"""Health check router."""

from fastapi import APIRouter

from fastapistock.schemas.common import ResponseEnvelope

router = APIRouter(tags=['health'])


@router.get('/health', response_model=ResponseEnvelope[dict[str, str]])
def health_check() -> ResponseEnvelope[dict[str, str]]:
    """Return a liveness signal.

    Returns:
        ResponseEnvelope with data={'status': 'ok'} on success.
    """
    return ResponseEnvelope(status='success', data={'status': 'ok'})
