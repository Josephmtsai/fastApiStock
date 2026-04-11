"""Service layer for portfolio PnL command."""

from fastapistock.repositories.portfolio_repo import fetch_pnl_tw, fetch_pnl_us


def _format_pnl_reply(tw_pnl: float | None, us_pnl: float | None) -> str:
    """Build the Telegram reply string for the /pnl command.

    Handles three cases: both values available, partial failure, total failure.
    Number format: sign always shown, thousands comma, no decimals.

    Args:
        tw_pnl: TW portfolio total unrealized PnL in TWD, or None if unavailable.
        us_pnl: US portfolio total unrealized PnL in TWD, or None if unavailable.

    Returns:
        Formatted reply string for the Telegram chat.
    """
    header = '📈 投資組合未實現損益'

    if tw_pnl is None and us_pnl is None:
        return f'{header}\n\n無法取得損益資料，請稍後再試'

    tw_line = (
        f'🇹🇼 台股：${tw_pnl:+,.0f} TWD' if tw_pnl is not None else '🇹🇼 台股：無法取得'
    )
    us_line = (
        f'🇺🇸 美股：${us_pnl:+,.0f} TWD' if us_pnl is not None else '🇺🇸 美股：無法取得'
    )

    if tw_pnl is not None and us_pnl is not None:
        total = tw_pnl + us_pnl
        total_line = f'合計：${total:+,.0f} TWD'
    else:
        total_line = '合計：無法計算（部分資料缺失）'

    return f'{header}\n\n{tw_line}\n{us_line}\n\n{total_line}'


def get_pnl_reply() -> str:
    """Fetch TW and US PnL and return a formatted Telegram reply string.

    Returns:
        Formatted reply string for the /pnl Telegram command.
    """
    tw = fetch_pnl_tw()
    us = fetch_pnl_us()
    return _format_pnl_reply(tw, us)
