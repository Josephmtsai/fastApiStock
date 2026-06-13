"""Service for building the daily P&L + news sentiment Telegram report."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Literal

from fastapistock.repositories import portfolio_repo
from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.repositories.twstock_repo import StockNotFoundError
from fastapistock.schemas.stock import RichStockData
from fastapistock.services import stock_service, us_stock_service
from fastapistock.services.fx_service import get_usd_twd_rate
from fastapistock.services.news_service import get_sentiment_news

logger = logging.getLogger(__name__)

_MSG_LIMIT = 4096
_MD_SPECIAL = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')


def _esc(text: str) -> str:
    """Escape MarkdownV2 special characters.

    Args:
        text: Raw string to escape.

    Returns:
        String with all MarkdownV2 special characters backslash-escaped.
    """
    return _MD_SPECIAL.sub(r'\\\1', text)


def _held_stocks(stocks: list[RichStockData]) -> list[RichStockData]:
    """Return only stocks with a positive share count.

    Args:
        stocks: List of RichStockData instances.

    Returns:
        Filtered list excluding stocks with None or zero shares.
    """
    return [s for s in stocks if s.shares is not None and s.shares > 0]


def _calc_market_today_pnl(stocks: list[RichStockData]) -> float:
    """Sum today's P&L across held stocks: change x shares.

    Args:
        stocks: List of held RichStockData instances.

    Returns:
        Total today's P&L as a float; 0.0 for empty input.
    """
    return sum(s.change * (s.shares or 0) for s in stocks)


def _calc_holding_pnl(stocks: list[RichStockData]) -> float:
    """Sum unrealized (holding) P&L across held stocks.

    Args:
        stocks: List of held RichStockData instances.

    Returns:
        Total unrealized P&L as a float; 0.0 when stocks is empty or
        all unrealized_pnl values are None.
    """
    return sum(s.unrealized_pnl or 0.0 for s in stocks)


def _fmt_tw_amount(amount: float) -> str:
    """Format a TWD amount with sign prefix.

    Args:
        amount: The amount in New Taiwan Dollars.

    Returns:
        Formatted string such as '+NT$12,450' or '-NT$800'.
    """
    sign = '+' if amount >= 0 else ''
    return f'{sign}NT${amount:,.0f}'


def _fmt_us_amount(amount: float) -> str:
    """Format a USD amount with sign prefix.

    Args:
        amount: The amount in US Dollars.

    Returns:
        Formatted string such as '+US$320.00' or '-US$800.00'.
    """
    sign = '+' if amount >= 0 else ''
    return f'{sign}US${amount:,.2f}'


def _fmt_us_today_line(us_today: float, rate: float | None) -> str:
    """Build the 美股今日 amount portion with optional TWD annotation.

    When *rate* is provided, appends ``(≈NT$xx,xxx)`` after the USD amount.
    The returned string is **unescaped**; callers must apply ``_esc()`` before
    embedding in a MarkdownV2 message.

    Args:
        us_today: US daily P&L in USD.
        rate: USD/TWD exchange rate, or None if unavailable.

    Returns:
        Raw (unescaped) amount string, e.g. ``'+US$1,257.93 (≈NT$40,883)'``
        or ``'+US$1,257.93'`` when rate is None.
    """
    usd_str = _fmt_us_amount(us_today)
    if rate is None:
        return usd_str
    twd_amount = round(us_today * rate)
    sign = '+' if twd_amount >= 0 else ''
    twd_str = f'{sign}{twd_amount:,.0f}'
    return f'{usd_str} (≈NT${twd_str})'


def _split_message(text: str) -> list[str]:
    """Split *text* into segments of at most _MSG_LIMIT chars, breaking at newlines.

    Args:
        text: Full message text.

    Returns:
        List of message segments, each at most 4096 characters.
    """
    if len(text) <= _MSG_LIMIT:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > _MSG_LIMIT and current:
            parts.append(''.join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        parts.append(''.join(current))
    return parts


def _build_stock_row(
    stock: RichStockData,
    market: Literal['TW', 'US'],
) -> str:
    """Build a MarkdownV2 row for one held stock.

    Args:
        stock: RichStockData instance for the stock.
        market: 'TW' or 'US' market identifier.

    Returns:
        Multi-line MarkdownV2 string with price, change, P&L, and news.
    """
    lines: list[str] = []

    name = _esc(stock.display_name) if stock.display_name != stock.symbol else ''
    header = f'*{_esc(stock.symbol)}*' + (f' {name}' if name else '')
    lines.append(header)

    change_sign = '+' if stock.change >= 0 else ''
    price_line = (
        f'現價 {_esc(str(round(stock.price, 2)))} \\| '
        f'今日 {_esc(f"{change_sign}{round(stock.change, 2)}")} '
        f'\\({_esc(f"{change_sign}{round(stock.change_pct, 2)}%")}\\)'
    )
    lines.append(price_line)

    if stock.unrealized_pnl is not None:
        if market == 'TW':
            pnl_str = _fmt_tw_amount(stock.unrealized_pnl)
        else:
            pnl_str = _fmt_us_amount(stock.unrealized_pnl)
        lines.append(f'持倉損益 {_esc(pnl_str)}')

    try:
        news_items = get_sentiment_news(stock.symbol, market)
        if news_items:
            for item in news_items:
                lines.append(f'📰 {_esc(item.title)} \\[{_esc(item.sentiment)}\\]')
        else:
            lines.append('📰 暫無新聞')
    except Exception as exc:
        logger.warning('News fetch failed for %s: %s', stock.symbol, exc)
        lines.append('📰 暫無新聞')

    return '\n'.join(lines)


def _build_market_section(
    stocks: list[RichStockData],
    market: Literal['TW', 'US'],
) -> str:
    """Build the market section block for TW or US holdings.

    Args:
        stocks: All stocks for the market (held and not held).
        market: 'TW' or 'US'.

    Returns:
        MarkdownV2 section string with separator, header, and per-stock rows.
    """
    held = _held_stocks(stocks)
    flag = '🇹🇼 台股明細' if market == 'TW' else '🇺🇸 美股明細'
    if not held:
        label = '目前無持股' if market == 'TW' else 'No holdings'
        return f'\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n{flag}\n\n{label}'
    rows = '\n\n'.join(_build_stock_row(s, market) for s in held)
    return f'\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n{flag}\n\n{rows}'


def build_pnl_report(now: datetime) -> list[str]:
    """Build the daily P&L + news report as a list of MarkdownV2 message segments.

    Args:
        now: Current datetime in Asia/Taipei timezone.

    Returns:
        List of MarkdownV2 strings, each at most 4096 chars.
    """
    date_str = now.strftime('%Y\\-%m\\-%d')
    sections: list[str] = [f'📊 *每日損益報告 {date_str}*']

    # --- TW ---
    tw_stocks: list[RichStockData] | None
    tw_portfolio_entries: dict[str, PortfolioEntry]
    try:
        tw_portfolio_entries = portfolio_repo.fetch_portfolio()
        tw_symbols_list: list[str] | None = list(tw_portfolio_entries.keys())
    except Exception as exc:
        logger.error('TW portfolio fetch failed: %s', exc)
        tw_portfolio_entries = {}
        tw_symbols_list = None

    if tw_symbols_list is None:
        tw_stocks = None
    elif not tw_symbols_list:
        tw_stocks = []
    else:
        tw_stocks = []
        for sym in tw_symbols_list:
            try:
                result = stock_service.get_rich_tw_stock(sym)
                entry = tw_portfolio_entries.get(sym)
                if entry is not None:
                    result = result.model_copy(
                        update={
                            'shares': entry.shares,
                            'avg_cost': entry.avg_cost,
                            'unrealized_pnl': entry.unrealized_pnl,
                        }
                    )
                tw_stocks.append(result)
            except StockNotFoundError:
                logger.warning('TW stock not found, skipping: %s', sym)
            except Exception as exc:
                logger.warning('TW stock fetch failed for %s: %s', sym, exc)

    # --- US ---
    us_stocks: list[RichStockData] | None
    try:
        us_symbols = list(portfolio_repo.fetch_portfolio_us().keys())
        us_stocks = us_stock_service.get_us_stocks(us_symbols) if us_symbols else []
    except Exception as exc:
        logger.error('US portfolio fetch failed: %s', exc)
        us_stocks = None

    # --- Account summary ---
    tw_held = _held_stocks(tw_stocks) if tw_stocks is not None else []
    us_held = _held_stocks(us_stocks) if us_stocks is not None else []
    tw_today: float | None = (
        _calc_market_today_pnl(tw_held) if tw_stocks is not None else None
    )
    us_today: float | None = (
        _calc_market_today_pnl(us_held) if us_stocks is not None else None
    )
    tw_holding_part = (
        f' ｜ 持倉：{_esc(_fmt_tw_amount(_calc_holding_pnl(tw_held)))}'
        if tw_held
        else ''
    )
    us_holding_part = (
        f' ｜ 持倉：{_esc(_fmt_us_amount(_calc_holding_pnl(us_held)))}'
        if us_held
        else ''
    )

    fx_rate: float | None = None
    try:
        fx_rate = get_usd_twd_rate()
    except Exception:
        logger.warning('FX rate fetch raised unexpectedly; falling back to USD-only')

    tw_line = (
        f'🇹🇼 台股今日：{_esc(_fmt_tw_amount(tw_today))}{tw_holding_part}'
        if tw_today is not None
        else '🇹🇼 台股：資料讀取失敗'
    )
    us_line = (
        f'🇺🇸 美股今日：{_esc(_fmt_us_today_line(us_today, fx_rate))}{us_holding_part}'
        if us_today is not None
        else '🇺🇸 美股：資料讀取失敗'
    )
    sections.append(f'💰 *帳戶總覽*\n{tw_line}\n{us_line}')

    # --- Stock sections ---
    if tw_stocks is not None:
        sections.append(_build_market_section(tw_stocks, 'TW'))
    else:
        sections.append(
            '\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n🇹🇼 台股明細\n\n資料讀取失敗'
        )

    if us_stocks is not None:
        sections.append(_build_market_section(us_stocks, 'US'))
    else:
        sections.append(
            '\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n🇺🇸 美股明細\n\n資料讀取失敗'
        )

    full_text = '\n\n'.join(sections)
    return _split_message(full_text)
