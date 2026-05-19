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


def format_market_daily_pnl_delta(
    *,
    market: str,
    current_pnl: float | None,
    previous_pnl: float | None,
) -> str:
    """Format one market's daily PnL delta versus its previous close baseline.

    Args:
        market: Market code, either ``TW`` or ``US``.
        current_pnl: Current market total PnL in TWD.
        previous_pnl: Market previous-close baseline PnL in TWD.

    Returns:
        Plain-text Telegram message body.

    Raises:
        ValueError: If market is not TW or US.
    """
    normalized = market.strip().upper()
    if normalized not in {'TW', 'US'}:
        raise ValueError(f'Unsupported market: {market}')

    lines = [f'{normalized} PnL vs previous close', '']
    if current_pnl is None:
        lines.append(f'{normalized} current PnL unavailable.')
        return '\n'.join(lines)

    if previous_pnl is None:
        lines.append(f'No {normalized} previous-close baseline yet.')
        lines.append(f'Current: {_fmt_twd(current_pnl)}')
        return '\n'.join(lines)

    lines.append(f'Current: {_fmt_twd(current_pnl)}')
    lines.append(f'Previous close: {_fmt_twd(previous_pnl)}')
    lines.append(f'Change: {_fmt_twd(current_pnl - previous_pnl)}')
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
    market: str,
    trading_date: str,
) -> str:
    """Build one market's daily PnL delta text.

    Args:
        market: Market code, either ``TW`` or ``US``.
        trading_date: Baseline trading date in ``YYYY-MM-DD`` format.

    Returns:
        Plain-text Telegram message body.

    Raises:
        ValueError: If market is not TW or US.
    """
    normalized = market.strip().upper()
    if normalized == 'TW':
        current = fetch_pnl_tw()
    elif normalized == 'US':
        current = fetch_pnl_us()
    else:
        raise ValueError(f'Unsupported market: {market}')

    snapshot = portfolio_snapshot_repo.get_daily(normalized, trading_date)
    previous = None
    if snapshot is not None:
        previous = snapshot.pnl_tw if normalized == 'TW' else snapshot.pnl_us

    return format_market_daily_pnl_delta(
        market=normalized,
        current_pnl=current,
        previous_pnl=previous,
    )
