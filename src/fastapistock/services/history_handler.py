"""Telegram ``/history`` command + inline-keyboard interaction (spec-006 D).

The Telegram webhook delegates here for both:

* Plain-text fallback: ``/history``, ``/history 2330``, ``/history us AAPL``.
* Inline-keyboard ``callback_query`` updates whose ``data`` matches the
  ``hist:*`` prefix grammar (see :data:`CALLBACK_PREFIX`).

State is kept entirely inside ``callback_data`` so the bot is stateless: each
button records every selection made so far. The 64-byte Telegram limit is
comfortable for our longest payload (``hist:p:symbol:TW:2330:monthly`` ≈ 28).

Callback grammar
----------------

::

    hist:t:summary                       # type-select → summary path
    hist:t:symbol                        # type-select → symbol path
    hist:m:summary:TW|US|ALL             # market-select on summary path
    hist:m:symbol:TW|US                  # market-select on symbol path
    hist:s:<market>:<symbol>             # symbol-select on symbol path
    hist:p:summary:<market|ALL>:<period> # final → render summary
    hist:p:symbol:<market>:<symbol>:<p>  # final → render symbol series
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapistock.repositories import report_history_repo
from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
)
from fastapistock.services import telegram_service

logger = logging.getLogger(__name__)

CALLBACK_PREFIX: str = 'hist:'
_TZ = ZoneInfo('Asia/Taipei')

_PeriodLiteral = Literal['weekly', 'monthly']
_MarketLiteral = Literal['TW', 'US']
_MarketOrAll = Literal['TW', 'US', 'ALL']

_SYMBOL_BUTTONS_PER_ROW = 3
_MAX_SYMBOL_BUTTONS = 18  # 6 rows × 3 buttons; keeps message height reasonable
_DEFAULT_RECORDS_LIMIT = 12


# ── Plain-text fallback ────────────────────────────────────────────────────


def handle_text_command(*, chat_id: str, args: str) -> None:
    """Handle the plain-text variants of ``/history`` (spec-006 D fallback).

    ``/history`` (no args) launches the inline keyboard. Otherwise the args
    are parsed as ``[market] symbol`` and the per-symbol monthly series is
    rendered directly.

    Args:
        chat_id: Target Telegram chat ID (string form for the API call).
        args: Argument string trailing the ``/history`` token.
    """
    if not args.strip():
        _send_type_menu(chat_id)
        return
    market, symbol = _parse_text_args(args)
    if symbol is None:
        telegram_service.reply_to_chat(
            chat_id,
            '用法：/history 2330 或 /history us AAPL',
        )
        return
    rows = _fetch_symbol_rows(symbol=symbol, market=market)
    if not rows:
        telegram_service.reply_to_chat(chat_id, '查無資料')
        return
    text = _format_symbol_text(symbol=rows[0].symbol, market=rows[0].market, rows=rows)
    telegram_service.reply_to_chat(chat_id, text)


def _parse_text_args(args: str) -> tuple[_MarketLiteral | None, str | None]:
    """Parse ``/history`` argument string into ``(market, symbol)``.

    Recognised forms:

    * ``2330`` — symbol only; market auto-detected later.
    * ``us AAPL`` / ``tw 2330`` — market prefix + symbol.

    Returns:
        ``(None, symbol)`` for symbol-only input or ``(market, symbol)`` for
        prefixed input. ``(None, None)`` on parse failure.
    """
    parts = args.strip().split()
    if len(parts) == 1:
        token = parts[0].strip().upper()
        if not token:
            return None, None
        return None, token
    if len(parts) >= 2:
        prefix = parts[0].strip().upper()
        symbol = parts[1].strip().upper()
        if prefix in {'TW', 'US'} and symbol:
            return prefix, symbol  # type: ignore[return-value]
    return None, None


def _fetch_symbol_rows(
    *,
    symbol: str,
    market: _MarketLiteral | None,
) -> list[SymbolSnapshot]:
    """Resolve ``(symbol, market)`` and load the per-symbol monthly series.

    When ``market`` is ``None`` the helper tries TW first, then US (spec D
    fallback policy) and returns whichever has data.
    """
    if market is not None:
        return report_history_repo.list_symbol_history(
            symbol=symbol,
            market=market,
            report_type='monthly',
            limit=_DEFAULT_RECORDS_LIMIT,
        )
    rows = report_history_repo.list_symbol_history(
        symbol=symbol,
        market='TW',
        report_type='monthly',
        limit=_DEFAULT_RECORDS_LIMIT,
    )
    if rows:
        return rows
    return report_history_repo.list_symbol_history(
        symbol=symbol,
        market='US',
        report_type='monthly',
        limit=_DEFAULT_RECORDS_LIMIT,
    )


# ── Callback query (inline keyboard) ───────────────────────────────────────


def handle_callback(
    *,
    chat_id: int,
    message_id: int,
    callback_query_id: str,
    data: str,
) -> None:
    """Dispatch a parsed ``callback_query`` to the appropriate keyboard step.

    Always answers the callback query first (clears the spinner) so the user
    gets immediate visual feedback even if rendering fails.

    Args:
        chat_id: Chat that received the callback (used to edit the message).
        message_id: ID of the bot message bearing the inline keyboard.
        callback_query_id: ID needed to acknowledge the callback.
        data: Raw ``callback_data`` string sent from Telegram.
    """
    telegram_service.answer_callback_query(callback_query_id)
    if not data.startswith(CALLBACK_PREFIX):
        logger.warning('history_callback.unknown_prefix data=%r', data)
        return
    parts = data.split(':')
    # parts[0] == 'hist'; parts[1] == step
    if len(parts) < 3:
        logger.warning('history_callback.malformed data=%r', data)
        return
    step = parts[1]
    if step == 't':
        _step_select_market(chat_id, message_id, parts)
    elif step == 'm':
        _step_after_market(chat_id, message_id, parts)
    elif step == 's':
        _step_select_period_for_symbol(chat_id, message_id, parts)
    elif step == 'p':
        _step_render_result(chat_id, message_id, parts)
    else:
        logger.warning('history_callback.unknown_step data=%r', data)


def _step_select_market(
    chat_id: int,
    message_id: int,
    parts: list[str],
) -> None:
    """Render the market-selection menu (after type pick)."""
    if len(parts) < 3:
        return
    flow = parts[2]
    if flow == 'summary':
        keyboard = _build_inline_keyboard(
            [
                [('全部', 'hist:m:summary:ALL')],
                [('TW', 'hist:m:summary:TW'), ('US', 'hist:m:summary:US')],
            ]
        )
        telegram_service.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text='請選市場：',
            reply_markup=keyboard,
        )
    elif flow == 'symbol':
        keyboard = _build_inline_keyboard(
            [[('TW', 'hist:m:symbol:TW'), ('US', 'hist:m:symbol:US')]]
        )
        telegram_service.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text='請選市場：',
            reply_markup=keyboard,
        )


def _step_after_market(
    chat_id: int,
    message_id: int,
    parts: list[str],
) -> None:
    """Branch to period menu (summary path) or symbol menu (symbol path)."""
    if len(parts) < 4:
        return
    flow = parts[2]
    market = parts[3]
    if flow == 'summary':
        keyboard = _build_inline_keyboard(
            [
                [
                    ('週', f'hist:p:summary:{market}:weekly'),
                    ('月', f'hist:p:summary:{market}:monthly'),
                ]
            ]
        )
        telegram_service.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text='請選週期：',
            reply_markup=keyboard,
        )
    elif flow == 'symbol':
        _render_symbol_picker(chat_id, message_id, market)


def _render_symbol_picker(
    chat_id: int,
    message_id: int,
    market: str,
) -> None:
    """Render the per-market symbol picker, sourcing options from the repo."""
    options = report_history_repo.list_options()
    symbols_map = options.get('symbols')
    symbols: list[str] = []
    if isinstance(symbols_map, dict):
        raw = symbols_map.get(market)
        if isinstance(raw, list):
            symbols = [s for s in raw if isinstance(s, str)]
    if not symbols:
        telegram_service.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f'{market} 目前沒有任何歷史資料',
        )
        return
    symbols = symbols[:_MAX_SYMBOL_BUTTONS]
    rows: list[list[tuple[str, str]]] = []
    for idx in range(0, len(symbols), _SYMBOL_BUTTONS_PER_ROW):
        chunk = symbols[idx : idx + _SYMBOL_BUTTONS_PER_ROW]
        rows.append([(sym, f'hist:s:{market}:{sym}') for sym in chunk])
    telegram_service.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text='請選股票：',
        reply_markup=_build_inline_keyboard(rows),
    )


def _step_select_period_for_symbol(
    chat_id: int,
    message_id: int,
    parts: list[str],
) -> None:
    """Render the period menu after a symbol pick (symbol flow)."""
    if len(parts) < 4:
        return
    market = parts[2]
    symbol = parts[3]
    keyboard = _build_inline_keyboard(
        [
            [
                ('週', f'hist:p:symbol:{market}:{symbol}:weekly'),
                ('月', f'hist:p:symbol:{market}:{symbol}:monthly'),
            ]
        ]
    )
    telegram_service.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f'請選週期 ({market} {symbol})：',
        reply_markup=keyboard,
    )


def _step_render_result(
    chat_id: int,
    message_id: int,
    parts: list[str],
) -> None:
    """Final step: query the repo and overwrite the message with results."""
    if len(parts) < 5:
        return
    flow = parts[2]
    if flow == 'summary':
        market_choice = parts[3]
        period = parts[4]
        if period not in {'weekly', 'monthly'}:
            return
        _render_summary(
            chat_id=chat_id,
            message_id=message_id,
            market_choice=market_choice,
            report_type=period,  # type: ignore[arg-type]
        )
    elif flow == 'symbol':
        if len(parts) < 6:
            return
        market = parts[3]
        symbol = parts[4]
        period = parts[5]
        if market not in {'TW', 'US'} or period not in {'weekly', 'monthly'}:
            return
        _render_symbol(
            chat_id=chat_id,
            message_id=message_id,
            market=market,  # type: ignore[arg-type]
            symbol=symbol,
            report_type=period,  # type: ignore[arg-type]
        )


def _render_summary(
    *,
    chat_id: int,
    message_id: int,
    market_choice: str,
    report_type: _PeriodLiteral,
) -> None:
    """Run the summary repo query and edit the bot message with the result."""
    market: _MarketLiteral | None = None
    if market_choice == 'TW':
        market = 'TW'
    elif market_choice == 'US':
        market = 'US'
    rows = report_history_repo.list_summary_history(
        report_type=report_type,
        market=market,
        limit=_DEFAULT_RECORDS_LIMIT,
    )
    if not rows:
        telegram_service.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text='查無資料',
        )
        return
    text = _format_summary_text(market=market, report_type=report_type, rows=rows)
    telegram_service.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
    )


def _render_symbol(
    *,
    chat_id: int,
    message_id: int,
    market: _MarketLiteral,
    symbol: str,
    report_type: _PeriodLiteral,
) -> None:
    """Run the per-symbol repo query and edit the bot message with the result."""
    rows = report_history_repo.list_symbol_history(
        symbol=symbol,
        market=market,
        report_type=report_type,
        limit=_DEFAULT_RECORDS_LIMIT,
    )
    if not rows:
        telegram_service.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text='查無資料',
        )
        return
    text = _format_symbol_text(
        symbol=symbol,
        market=market,
        rows=rows,
        report_type=report_type,
    )
    telegram_service.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
    )


# ── Formatting ─────────────────────────────────────────────────────────────


def _format_symbol_text(
    *,
    symbol: str,
    market: str,
    rows: list[SymbolSnapshot],
    report_type: _PeriodLiteral = 'monthly',
) -> str:
    """Render a per-symbol series as a short, fixed-width plain-text reply."""
    period_label = '週報' if report_type == 'weekly' else '月報'
    title = f'📈 {symbol} ({market}) 近 {len(rows)} 期{period_label}'
    body_lines: list[str] = [title, '']
    for row in rows:
        pnl = _format_decimal(row.unrealized_pnl, signed=True)
        pct = _format_decimal(row.pnl_pct, signed=True, suffix='%')
        delta = _format_decimal(row.pnl_delta, signed=True, prefix='Δ ')
        body_lines.append(f'{row.report_period}  {pnl}  ({pct}){delta}')
    return '\n'.join(body_lines)


def _format_summary_text(
    *,
    market: _MarketLiteral | None,
    report_type: _PeriodLiteral,
    rows: list[ReportSummary],
) -> str:
    """Render summary rows as plain-text. Dual market prints both PnL columns."""
    period_label = '週報' if report_type == 'weekly' else '月報'
    if market is None:
        title = f'📊 帳戶總覽 (TW + US) 近 {len(rows)} 期{period_label}'
    else:
        title = f'📊 {market} 帳戶 近 {len(rows)} 期{period_label}'
    body_lines: list[str] = [title, '']
    for row in rows:
        if market is None:
            tw = _format_decimal(row.pnl_tw_total, signed=True)
            us = _format_decimal(row.pnl_us_total, signed=True)
            body_lines.append(f'{row.report_period}  TW {tw}  US {us}')
        else:
            pnl = row.pnl_tw_total if market == 'TW' else row.pnl_us_total
            delta = row.pnl_tw_delta if market == 'TW' else row.pnl_us_delta
            pnl_str = _format_decimal(pnl, signed=True)
            delta_str = _format_decimal(delta, signed=True, prefix='Δ ')
            body_lines.append(f'{row.report_period}  {pnl_str}{delta_str}')
    return '\n'.join(body_lines)


def _format_decimal(
    value: Decimal | None,
    *,
    signed: bool = False,
    prefix: str = '',
    suffix: str = '',
) -> str:
    """Render a ``Decimal`` (or ``None``) as a short human-friendly string.

    Args:
        value: Number to render.
        signed: When ``True`` non-negative values are prefixed with ``+``.
        prefix: Literal prefix (e.g. ``'Δ '``); empty string when ``value`` is
            ``None`` to keep the column count stable.
        suffix: Literal suffix (e.g. ``'%'``).

    Returns:
        Formatted string. Returns ``'—'`` when ``value`` is ``None``.
    """
    if value is None:
        return '—' if not prefix else ''
    sign = '+' if (signed and value >= 0) else ''
    return f'{prefix}{sign}{value:,.2f}{suffix}'


# ── Inline keyboard helpers ────────────────────────────────────────────────


def _build_inline_keyboard(
    rows: list[list[tuple[str, str]]],
) -> dict[str, object]:
    """Construct a Telegram ``inline_keyboard`` payload."""
    return {
        'inline_keyboard': [
            [{'text': label, 'callback_data': data} for label, data in row]
            for row in rows
        ]
    }


def _send_type_menu(chat_id: str) -> None:
    """First-step menu: type selection (summary vs. symbol)."""
    keyboard = _build_inline_keyboard(
        [
            [
                ('帳戶總覽', 'hist:t:summary'),
                ('個股查詢', 'hist:t:symbol'),
            ]
        ]
    )
    telegram_service.reply_to_chat(
        chat_id,
        '請選擇查詢類型：',
        reply_markup=keyboard,
    )


# Currently unused but exposed for potential timestamp logging callers.
def _now() -> datetime:
    """Return Asia/Taipei now (kept here so tests can monkeypatch)."""
    return datetime.now(_TZ)
