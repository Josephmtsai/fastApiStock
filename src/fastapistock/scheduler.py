"""APScheduler configuration and scheduled push logic.

Runs inside the FastAPI process via the lifespan context manager.
A single interval job fires every 30 minutes; time-window functions
decide which market (if any) to push to Telegram.
"""

import logging
from datetime import date, datetime, timedelta
from functools import partial
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from fastapistock.config import TELEGRAM_USER_ID, tw_stock_codes, us_stock_symbols
from fastapistock.services import portfolio_service
from fastapistock.services.report_service import run_report_pipeline
from fastapistock.services.telegram_service import send_text_message

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


def capture_tw_close_snapshot(now: datetime | None = None) -> None:
    """Capture TW close PnL baseline for the current Taiwan trading date.

    Args:
        now: Optional Asia/Taipei timestamp for tests.
    """
    local = (now or datetime.now(_TZ)).astimezone(_TZ)
    try:
        portfolio_service.save_daily_close_snapshot(
            market='TW',
            trading_date=local.date().isoformat(),
            captured_at=local,
        )
    except Exception:
        logger.exception('TW daily close snapshot failed')


def capture_us_close_snapshot(now: datetime | None = None) -> None:
    """Capture US close PnL baseline for the previous US trading date.

    Args:
        now: Optional Asia/Taipei timestamp for tests.
    """
    local = (now or datetime.now(_TZ)).astimezone(_TZ)
    trading_date = (local.date() - timedelta(days=1)).isoformat()
    try:
        portfolio_service.save_daily_close_snapshot(
            market='US',
            trading_date=trading_date,
            captured_at=local,
        )
    except Exception:
        logger.exception('US daily close snapshot failed')


def _previous_tw_trading_date(now: datetime) -> str:
    """Return the TW baseline trading date to compare against."""
    local_date = now.astimezone(_TZ).date()
    return _previous_weekday(local_date).isoformat()


def _previous_us_trading_date(now: datetime) -> str:
    """Return the US baseline trading date to compare against."""
    local = now.astimezone(_TZ)
    if local.hour <= 4:
        session_date = local.date() - timedelta(days=1)
        return _previous_weekday(session_date).isoformat()
    return _previous_weekday(local.date()).isoformat()


def _previous_weekday(current_date: date) -> date:
    """Return the previous weekday, ignoring market holidays."""
    candidate = current_date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _send_daily_pnl_delta(market: str, now: datetime | None = None) -> None:
    """Send compact PnL delta message after scheduled quote push."""
    if not TELEGRAM_USER_ID:
        logger.warning('TELEGRAM_USER_ID not set; skipping PnL delta push')
        return
    normalized = market.strip().upper()
    local = (now or datetime.now(_TZ)).astimezone(_TZ)
    if normalized == 'TW':
        trading_date = _previous_tw_trading_date(local)
    elif normalized == 'US':
        trading_date = _previous_us_trading_date(local)
    else:
        raise ValueError(f'Unsupported market: {market}')
    text = portfolio_service.get_daily_pnl_delta_reply(
        market=normalized,
        trading_date=trading_date,
    )
    if text:
        send_text_message(TELEGRAM_USER_ID, text)


def _safe_send_daily_pnl_delta(market: str) -> None:
    """Send PnL delta without letting failures interrupt scheduled pushes."""
    try:
        _send_daily_pnl_delta(market)
    except Exception:
        logger.exception('Scheduled PnL delta wrapper failed')


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
        _safe_send_daily_pnl_delta('TW')

    if is_us_market_window(now):
        logger.info('US market window active — pushing')
        push_us_stocks()
        _safe_send_daily_pnl_delta('US')


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
    scheduler.add_job(
        partial(run_report_pipeline, report_type='weekly', trigger='cron'),
        trigger=CronTrigger(day_of_week='sun', hour=21, minute=0, timezone=str(_TZ)),
        id='weekly_report',
        name='Weekly portfolio report',
        replace_existing=True,
    )
    scheduler.add_job(
        capture_tw_close_snapshot,
        trigger=CronTrigger(
            day_of_week='mon-fri', hour=14, minute=10, timezone=str(_TZ)
        ),
        id='tw_daily_close_snapshot',
        name='TW daily close PnL snapshot',
        replace_existing=True,
    )
    scheduler.add_job(
        capture_us_close_snapshot,
        trigger=CronTrigger(
            day_of_week='tue-sat', hour=4, minute=10, timezone=str(_TZ)
        ),
        id='us_daily_close_snapshot',
        name='US daily close PnL snapshot',
        replace_existing=True,
    )
    scheduler.add_job(
        partial(run_report_pipeline, report_type='monthly', trigger='cron'),
        trigger=CronTrigger(
            day_of_week='sun', day='1-7', hour=21, minute=0, timezone=str(_TZ)
        ),
        id='monthly_report',
        name='Monthly portfolio report (first Sunday)',
        replace_existing=True,
    )
    return scheduler
