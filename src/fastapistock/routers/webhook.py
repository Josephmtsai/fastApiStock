"""Router for Telegram Bot webhook endpoint.

Receives incoming Telegram updates via POST /api/v1/webhook/telegram.
Validates the secret token, checks the authorized user ID, dispatches
commands (/q, /us, /tw, /help) to the appropriate service, and replies
via the Telegram sendMessage API.

Rate limiting uses the RATE_LIMIT_WEBHOOK_* env var prefix.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request

from fastapistock import config
from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.schemas.common import ResponseEnvelope
from fastapistock.services.telegram_service import (
    format_rich_stock_message,
    reply_to_chat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/webhook', tags=['webhook'])

# ---------------------------------------------------------------------------
# Telegram Update Pydantic models
# ---------------------------------------------------------------------------
from zoneinfo import ZoneInfo  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402


class TelegramFrom(BaseModel):
    """Telegram message sender identity."""

    id: int
    is_bot: bool = False
    first_name: str = ''


class TelegramChat(BaseModel):
    """Telegram chat context (used to send the reply)."""

    id: int


class TelegramMessage(BaseModel):
    """A single Telegram message object inside an Update."""

    message_id: int
    from_: TelegramFrom | None = Field(default=None, alias='from')
    chat: TelegramChat
    text: str | None = None

    model_config = {'populate_by_name': True}


class TelegramUpdate(BaseModel):
    """Top-level Telegram Bot API Update object."""

    update_id: int
    message: TelegramMessage | None = None


# ---------------------------------------------------------------------------
# Helper: progress bar
# ---------------------------------------------------------------------------

_BAR_LENGTH = 10


def _progress_bar(rate_pct: float) -> str:
    """Build a 10-block Unicode progress bar for the given percentage.

    Args:
        rate_pct: Achievement rate in percent (may exceed 100).

    Returns:
        String of filled (▓) and empty (░) blocks, e.g. '▓▓▓▓▓░░░░░'.
    """
    filled = min(_BAR_LENGTH, round(rate_pct / _BAR_LENGTH))
    return '▓' * filled + '░' * (_BAR_LENGTH - filled)


# ---------------------------------------------------------------------------
# Helper: parse command + args from message text
# ---------------------------------------------------------------------------


def _parse_command(text: str) -> tuple[str, str]:
    """Extract the command and its argument string from a message.

    Strips optional ``@bot_name`` suffix from the command token.

    Args:
        text: Raw message text, e.g. '/us@MyBot AAPL,TSLA'.

    Returns:
        Tuple of (command, args), e.g. ('/us', 'AAPL,TSLA').
        Returns ('', '') for empty input.
    """
    parts = text.strip().split(None, 1)
    if not parts:
        return '', ''
    cmd = parts[0].split('@')[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ''
    return cmd, args


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

_HELP_TEXT = (
    '📋 可用指令\n\n'
    '/q — 本季投資達成率\n'
    '/pnl — 投資組合未實現損益（台股＋美股）\n'
    '/us AAPL,TSLA — 美股即時報價\n'
    '/tw 0050,2330 — 台股即時報價\n'
    '/help — 顯示此說明'
)

_US_USAGE = '用法：/us AAPL,TSLA\n請提供至少一個美股代號（以逗號分隔）'
_TW_USAGE = '用法：/tw 0050,2330\n請提供至少一個台股代號（以逗號分隔）'


def _handle_q() -> str:
    """Compute and format the quarterly investment achievement rate reply.

    Returns:
        Formatted reply string for the /q command.
    """
    from datetime import date

    from fastapistock.services.investment_plan_service import (
        format_achievement_reply,
        get_quarterly_achievement_rate,
    )

    today = date.today()
    report = get_quarterly_achievement_rate(today)
    return format_achievement_reply(report)


def _handle_us(args: str) -> str:
    """Fetch US stock data and format it as a reply string.

    Args:
        args: Comma-separated US ticker symbols (raw, may be empty).

    Returns:
        Formatted stock reply or error/usage text.
    """
    from datetime import datetime

    from fastapistock.services.us_stock_service import get_us_stocks

    symbols = [s.strip().upper() for s in args.split(',') if s.strip().isalpha()]
    if not symbols:
        return _US_USAGE

    try:
        stocks = get_us_stocks(symbols)
    except StockNotFoundError as exc:
        logger.warning('US stock not found in webhook: %s', exc)
        return str(exc)

    if not stocks:
        return '查無美股資料'

    now = datetime.now(ZoneInfo('Asia/Taipei'))
    return format_rich_stock_message(stocks, 'US', now)


def _handle_tw(args: str) -> str:
    """Fetch Taiwan stock data and format it as a reply string.

    Args:
        args: Comma-separated Taiwan stock codes (raw, may be empty).

    Returns:
        Formatted stock reply or error/usage text.
    """
    from datetime import datetime

    from fastapistock.services.stock_service import get_rich_tw_stocks

    codes = [c.strip() for c in args.split(',') if c.strip().isdigit()]
    if not codes:
        return _TW_USAGE

    try:
        stocks = get_rich_tw_stocks(codes)
    except StockNotFoundError as exc:
        logger.warning('TW stock not found in webhook: %s', exc)
        return str(exc)

    if not stocks:
        return '查無台股資料'

    now = datetime.now(ZoneInfo('Asia/Taipei'))
    return format_rich_stock_message(stocks, 'TW', now)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@router.post(
    '/telegram',
    response_model=ResponseEnvelope[None],
    summary='Receive Telegram Bot webhook updates',
)
async def receive_telegram_update(
    update: TelegramUpdate,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> ResponseEnvelope[None]:
    """Handle incoming Telegram Bot API webhook updates.

    Validates the secret token, checks the sender's user ID against the
    configured ``TELEGRAM_USER_ID``, then dispatches the recognized command
    to the appropriate service.  Unrecognized messages and unauthorized
    senders are silently ignored (HTTP 200) so Telegram does not retry.

    Args:
        update: Parsed Telegram Update payload.
        request: Raw FastAPI request (unused; present for middleware compat).
        x_telegram_bot_api_secret_token: Value of the Telegram secret header.

    Returns:
        ResponseEnvelope with status 'success' in all non-403 cases.

    Raises:
        HTTPException: 403 when the secret token is missing or incorrect.
    """
    # 1. Validate secret token
    if x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET:
        logger.warning('Webhook secret mismatch — rejecting request')
        raise HTTPException(status_code=403, detail='Invalid webhook secret')

    # 2. Ignore non-message updates (callback_query, etc.)
    if update.message is None:
        return ResponseEnvelope(status='success', message='ok')

    msg = update.message
    sender = msg.from_

    # 3. Check authorized user
    authorized_id = config.TELEGRAM_USER_ID
    if not authorized_id or str(getattr(sender, 'id', '')) != authorized_id:
        logger.info(
            'Ignoring message from unauthorized user_id=%s', getattr(sender, 'id', None)
        )
        return ResponseEnvelope(status='success', message='ok')

    # 4. Ignore non-text messages
    if not msg.text:
        return ResponseEnvelope(status='success', message='ok')

    cmd, args = _parse_command(msg.text)
    chat_id = str(msg.chat.id)

    # 5. Dispatch command
    if cmd == '/q':
        reply = _handle_q()
    elif cmd == '/pnl':
        from fastapistock.services.portfolio_service import get_pnl_reply

        reply = get_pnl_reply()
    elif cmd == '/us':
        reply = _handle_us(args)
    elif cmd == '/tw':
        reply = _handle_tw(args)
    elif cmd == '/help':
        reply = _HELP_TEXT
    else:
        # Unrecognized — silently ignore
        return ResponseEnvelope(status='success', message='ok')

    reply_to_chat(chat_id, reply)
    return ResponseEnvelope(status='success', message='ok')
