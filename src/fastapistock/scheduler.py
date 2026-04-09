"""APScheduler configuration and scheduled push logic.

Runs inside the FastAPI process via the lifespan context manager.
A single interval job fires every 30 minutes; time-window functions
decide which market (if any) to push to Telegram.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from fastapistock.config import TELEGRAM_USER_ID, tw_stock_codes, us_stock_symbols

logger = logging.getLogger(__name__)

_TZ = ZoneInfo('Asia/Taipei')


def is_tw_market_window(now: datetime) -> bool:
    """Return True when *now* falls in the Taiwan stock push window.

    Window: Monday–Friday, 08:30–14:00 Asia/Taipei (inclusive).

    Args:
        now: Current datetime; must already be in Asia/Taipei timezone.

    Returns:
        True if a Taiwan stock push should be sent.
    """
    if now.weekday() > 4:  # Saturday=5, Sunday=6
        return False
    minutes = now.hour * 60 + now.minute
    return 8 * 60 + 30 <= minutes <= 14 * 60


def is_us_market_window(now: datetime) -> bool:
    """Return True when *now* falls in the US stock push window.

    Window: Monday–Friday 17:00 onwards (start of US session in Taipei time)
    or Tuesday–Saturday 00:00–04:00 (overnight continuation).

    Args:
        now: Current datetime; must already be in Asia/Taipei timezone.

    Returns:
        True if a US stock push should be sent.
    """
    weekday = now.weekday()  # Mon=0 … Sun=6
    minutes = now.hour * 60 + now.minute
    if minutes >= 17 * 60:
        return weekday <= 4  # Mon–Fri evening
    if minutes <= 4 * 60:
        return 1 <= weekday <= 5  # Tue–Sat early morning
    return False


def push_tw_stocks() -> None:
    """Fetch configured Taiwan stocks and send a rich Telegram message.

    Reads TW_STOCKS and TELEGRAM_USER_ID from environment. Logs and returns
    early if either is missing. All exceptions are caught to prevent a single
    failure from stopping the scheduler.
    """
    if not TELEGRAM_USER_ID:
        logger.warning('TELEGRAM_USER_ID not set; skipping TW push')
        return
    codes = tw_stock_codes()
    if not codes:
        logger.warning('TW_STOCKS not configured; skipping TW push')
        return
    try:
        from fastapistock.services.stock_service import get_rich_tw_stocks
        from fastapistock.services.telegram_service import send_rich_stock_message

        stocks = get_rich_tw_stocks(codes)
        send_rich_stock_message(TELEGRAM_USER_ID, stocks, market='TW')
        logger.info('TW push complete: %d stocks sent', len(stocks))
    except Exception:
        logger.exception('TW scheduled push failed')


def push_us_stocks() -> None:
    """Fetch configured US stocks and send a rich Telegram message.

    Reads US_STOCKS and TELEGRAM_USER_ID from environment. Logs and returns
    early if either is missing. All exceptions are caught to prevent a single
    failure from stopping the scheduler.
    """
    if not TELEGRAM_USER_ID:
        logger.warning('TELEGRAM_USER_ID not set; skipping US push')
        return
    symbols = us_stock_symbols()
    if not symbols:
        logger.warning('US_STOCKS not configured; skipping US push')
        return
    try:
        from fastapistock.services.telegram_service import send_rich_stock_message
        from fastapistock.services.us_stock_service import get_us_stocks

        stocks = get_us_stocks(symbols)
        send_rich_stock_message(TELEGRAM_USER_ID, stocks, market='US')
        logger.info('US push complete: %d stocks sent', len(stocks))
    except Exception:
        logger.exception('US scheduled push failed')


def _scheduled_push() -> None:
    """Check time windows and trigger appropriate market pushes.

    Called by APScheduler every 30 minutes. Determines current Asia/Taipei
    time and delegates to push_tw_stocks() and/or push_us_stocks() as needed.
    """
    now = datetime.now(_TZ)
    logger.info('Scheduler tick at %s', now.strftime('%Y-%m-%d %H:%M %Z'))

    if is_tw_market_window(now):
        logger.info('TW market window active — pushing')
        push_tw_stocks()

    if is_us_market_window(now):
        logger.info('US market window active — pushing')
        push_us_stocks()


def build_scheduler() -> AsyncIOScheduler:
    """Create and configure an APScheduler AsyncIOScheduler.

    Adds a single interval job that fires every 30 minutes in the
    Asia/Taipei timezone. The scheduler is returned un-started; the
    caller (lifespan) is responsible for calling .start() and .shutdown().

    Returns:
        Configured AsyncIOScheduler, not yet started.
    """
    scheduler = AsyncIOScheduler(timezone=str(_TZ))
    scheduler.add_job(
        _scheduled_push,
        trigger=IntervalTrigger(minutes=30, timezone=str(_TZ)),
        id='stock_push',
        name='Scheduled stock push (TW + US)',
        replace_existing=True,
    )
    return scheduler
