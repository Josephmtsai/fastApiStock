"""Service layer for portfolio PnL command."""

from datetime import datetime

from fastapistock.repositories import portfolio_snapshot_repo
from fastapistock.repositories.portfolio_repo import fetch_pnl_tw, fetch_pnl_us
from fastapistock.repositories.portfolio_snapshot_repo import PortfolioSnapshot


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


def _fmt_twd(value: float) -> str:
    """Format a TWD amount with explicit sign."""
    sign = '+' if value >= 0 else '-'
    return f'{sign}{abs(value):,.0f} TWD'


def format_daily_pnl_delta(
    *,
    current_tw: float | None,
    current_us: float | None,
    previous_tw: float | None,
    previous_us: float | None,
) -> str:
    """Format daily PnL delta versus previous market-close baselines.

    Args:
        current_tw: Current TW total PnL in TWD.
        current_us: Current US total PnL in TWD.
        previous_tw: TW previous-close baseline PnL in TWD.
        previous_us: US previous-close baseline PnL in TWD.

    Returns:
        Plain-text Telegram message body.
    """
    lines = ['Portfolio PnL vs previous close', '']
    current_total = sum(
        value for value in (current_tw, current_us) if value is not None
    )

    if previous_tw is None and previous_us is None:
        lines.append('No previous-close baseline yet.')
        if current_tw is None or current_us is None:
            lines.append(
                'Current total unavailable until both markets have current PnL.'
            )
            return '\n'.join(lines)
        lines.append(f'Current total: {_fmt_twd(current_total)}')
        return '\n'.join(lines)

    if current_tw is not None and previous_tw is not None:
        lines.append(f'TW: {_fmt_twd(current_tw - previous_tw)}')
    else:
        lines.append('TW: current PnL or baseline unavailable')

    if current_us is not None and previous_us is not None:
        lines.append(f'US: {_fmt_twd(current_us - previous_us)}')
    else:
        lines.append('US: current PnL or baseline unavailable')

    lines.append('')
    if (
        current_tw is None
        or current_us is None
        or previous_tw is None
        or previous_us is None
    ):
        lines.append(
            'Total delta unavailable until both markets have current PnL and baselines.'
        )
        return '\n'.join(lines)

    previous_total = previous_tw + previous_us
    total_delta = current_total - previous_total
    lines.append(f'Total: {_fmt_twd(total_delta)}')
    lines.append(f'Current total: {_fmt_twd(current_total)}')
    lines.append(f'Previous close baseline: {_fmt_twd(previous_total)}')
    return '\n'.join(lines)


def save_daily_close_snapshot(
    *,
    market: str,
    trading_date: str,
    captured_at: datetime,
) -> bool:
    """Capture one market's close PnL baseline.

    Args:
        market: Market code, either ``TW`` or ``US``.
        trading_date: Market trading date in ``YYYY-MM-DD`` format.
        captured_at: Timestamp when the snapshot was captured.

    Returns:
        True when the snapshot was saved, False when current PnL was unavailable.

    Raises:
        ValueError: If market is not TW or US.
    """
    normalized = market.strip().upper()
    if normalized == 'TW':
        pnl_tw = fetch_pnl_tw()
        if pnl_tw is None:
            return False
        snapshot = PortfolioSnapshot(pnl_tw=pnl_tw, pnl_us=0.0, timestamp=captured_at)
    elif normalized == 'US':
        pnl_us = fetch_pnl_us()
        if pnl_us is None:
            return False
        snapshot = PortfolioSnapshot(pnl_tw=0.0, pnl_us=pnl_us, timestamp=captured_at)
    else:
        raise ValueError(f'Unsupported market: {market}')

    portfolio_snapshot_repo.save_daily(normalized, trading_date, snapshot)
    return True


def get_daily_pnl_delta_reply(
    *,
    tw_trading_date: str,
    us_trading_date: str,
) -> str:
    """Build daily PnL delta text using current PnL and close baselines.

    Args:
        tw_trading_date: TW baseline trading date in ``YYYY-MM-DD`` format.
        us_trading_date: US baseline trading date in ``YYYY-MM-DD`` format.

    Returns:
        Plain-text Telegram message body.
    """
    current_tw = fetch_pnl_tw()
    current_us = fetch_pnl_us()
    tw_snapshot = portfolio_snapshot_repo.get_daily('TW', tw_trading_date)
    us_snapshot = portfolio_snapshot_repo.get_daily('US', us_trading_date)
    return format_daily_pnl_delta(
        current_tw=current_tw,
        current_us=current_us,
        previous_tw=tw_snapshot.pnl_tw if tw_snapshot is not None else None,
        previous_us=us_snapshot.pnl_us if us_snapshot is not None else None,
    )
