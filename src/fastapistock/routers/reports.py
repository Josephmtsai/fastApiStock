"""Router for portfolio weekly/monthly report preview and dispatch endpoints.

All routes live under /api/v1/reports.  Rate limiting is applied globally by
the middleware layer in main.py via the ``/api/v1/reports`` prefix mapping,
not per-route.

Endpoints:
    GET  /api/v1/reports/weekly/preview   — render weekly text only
    GET  /api/v1/reports/monthly/preview  — render monthly text only
    POST /api/v1/reports/weekly/send      — render and dispatch to Telegram
    POST /api/v1/reports/monthly/send     — render and dispatch to Telegram
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from fastapistock.schemas.common import ResponseEnvelope
from fastapistock.services.report_service import (
    build_monthly_report,
    build_weekly_report,
    send_monthly_report,
    send_weekly_report,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/reports', tags=['reports'])

_TZ = ZoneInfo('Asia/Taipei')


@router.get(
    '/weekly/preview',
    response_model=ResponseEnvelope[dict[str, str]],
    summary='Render the weekly report without dispatching to Telegram',
)
async def preview_weekly() -> ResponseEnvelope[dict[str, str]]:
    """Build the weekly report text and return it in the response envelope.

    Returns:
        ResponseEnvelope carrying ``{'text': <MarkdownV2 body>}`` on success.
    """
    logger.info('Weekly report preview requested')
    text = build_weekly_report(datetime.now(_TZ))
    return ResponseEnvelope(status='success', data={'text': text})


@router.get(
    '/monthly/preview',
    response_model=ResponseEnvelope[dict[str, str]],
    summary='Render the monthly report without dispatching to Telegram',
)
async def preview_monthly() -> ResponseEnvelope[dict[str, str]]:
    """Build the monthly report text and return it in the response envelope.

    Returns:
        ResponseEnvelope carrying ``{'text': <MarkdownV2 body>}`` on success.
    """
    logger.info('Monthly report preview requested')
    text = build_monthly_report(datetime.now(_TZ))
    return ResponseEnvelope(status='success', data={'text': text})


@router.post(
    '/weekly/send',
    response_model=ResponseEnvelope[None],
    summary='Dispatch the weekly report to the configured Telegram chat',
)
async def trigger_weekly_send() -> ResponseEnvelope[None]:
    """Render and send the weekly report to Telegram.

    ``send_weekly_report`` never raises; any underlying error is logged and
    surfaced via the log stream. The endpoint always returns success once the
    dispatch attempt is scheduled.
    """
    logger.info('Weekly report dispatch requested')
    send_weekly_report()
    return ResponseEnvelope(status='success', message='weekly report dispatched')


@router.post(
    '/monthly/send',
    response_model=ResponseEnvelope[None],
    summary='Dispatch the monthly report to the configured Telegram chat',
)
async def trigger_monthly_send() -> ResponseEnvelope[None]:
    """Render and send the monthly report to Telegram.

    ``send_monthly_report`` never raises; any underlying error is logged and
    surfaced via the log stream. The endpoint always returns success once the
    dispatch attempt is scheduled.
    """
    logger.info('Monthly report dispatch requested')
    send_monthly_report()
    return ResponseEnvelope(status='success', message='monthly report dispatched')
