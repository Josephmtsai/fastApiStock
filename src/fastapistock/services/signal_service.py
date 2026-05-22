"""Service for Telegram /signal add-on signal overview."""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast

from fastapistock.repositories import portfolio_repo, signal_history_repo
from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.schemas.stock import RichStockData
from fastapistock.services import stock_service, us_stock_service
from fastapistock.services.telegram_service import _escape_md

logger = logging.getLogger(__name__)
Market = Literal['TW', 'US']
SignalState = Literal['深度加碼', '中度加碼', '輕度加碼', '觀察', '不加碼', '資料不足']
HistoryLabel = Literal['未觸發', '短期訊號', '訊號持續']


@dataclass(frozen=True)
class SignalStatus:
    """Evaluation result for one portfolio holding."""

    symbol: str
    market: Market
    status: SignalState
    price: float | None
    drop_pct: float | None
    ma50: float | None
    ma50_broken: bool | None
    reason: str
    history_count_90d: int
    history_label: HistoryLabel


def evaluate_signal_status(
    *,
    symbol: str,
    market: Market,
    price: float | None,
    week52_high: float | None,
    ma50: float | None,
    history_count_90d: int,
) -> SignalStatus:
    """Evaluate the current add-on signal state for one holding."""
    history_label = _history_label(history_count_90d)
    missing_reason = _missing_data_reason(price, week52_high, ma50)
    if missing_reason is not None:
        return SignalStatus(
            symbol=symbol,
            market=market,
            status='資料不足',
            price=price,
            drop_pct=None,
            ma50=ma50,
            ma50_broken=None,
            reason=missing_reason,
            history_count_90d=history_count_90d,
            history_label=history_label,
        )

    valid_price = cast(float, price)
    valid_high = cast(float, week52_high)
    valid_ma50 = cast(float, ma50)
    drop_pct = (valid_price - valid_high) / valid_high * 100
    ma50_broken = valid_price < valid_ma50
    status, reason = _classify_complete_data(market, drop_pct, ma50_broken)
    return SignalStatus(
        symbol=symbol,
        market=market,
        status=status,
        price=valid_price,
        drop_pct=drop_pct,
        ma50=valid_ma50,
        ma50_broken=ma50_broken,
        reason=reason,
        history_count_90d=history_count_90d,
        history_label=history_label,
    )


def build_signal_overview(now: datetime) -> str:
    """Build the MarkdownV2 `/signal` reply for all TW and US holdings."""
    counts = _load_history_counts(now)
    lines = [
        '*加碼訊號總覽*',
        _escape_md(now.strftime('%Y-%m-%d %H:%M Asia/Taipei')),
        '',
    ]
    lines.extend(
        _render_market_section(
            market='TW',
            title='台股',
            fetch_holdings=portfolio_repo.fetch_portfolio,
            fetch_stocks=stock_service.get_rich_tw_stocks,
            history_counts=counts,
        )
    )
    lines.append('')
    lines.extend(
        _render_market_section(
            market='US',
            title='美股',
            fetch_holdings=portfolio_repo.fetch_portfolio_us,
            fetch_stocks=us_stock_service.get_us_stocks,
            history_counts=counts,
        )
    )
    return '\n'.join(lines)


def _load_history_counts(now: datetime) -> Counter[tuple[str, str]]:
    start_date = now.date() - timedelta(days=90)
    end_date = now.date()
    counts: Counter[tuple[str, str]] = Counter()
    try:
        records = signal_history_repo.list_signals(start_date, end_date)
    except Exception as exc:
        logger.exception('Failed to read signal history: %s', exc)
        return counts
    for record in records:
        counts[(record.market.upper(), record.symbol.upper())] += 1
    return counts


def _render_market_section(
    *,
    market: Market,
    title: str,
    fetch_holdings: Callable[[], dict[str, PortfolioEntry]],
    fetch_stocks: Callable[[list[str]], list[RichStockData]],
    history_counts: Counter[tuple[str, str]],
) -> list[str]:
    lines = [f'*{_escape_md(title)}*']
    try:
        holdings = fetch_holdings()
        symbols = list(holdings)
    except Exception as exc:
        logger.exception('Failed to render %s signal section: %s', market, exc)
        return [*lines, '資料讀取失敗']
    if not symbols:
        return [*lines, '目前無持股資料']
    stocks = _fetch_stock_snapshots(market, symbols, fetch_stocks)
    stock_by_symbol = {stock.symbol.upper(): stock for stock in stocks}
    for symbol in symbols:
        count = history_counts[(market, symbol.upper())]
        status = _status_from_stock(
            symbol,
            market,
            stock_by_symbol.get(symbol.upper()),
            count,
        )
        lines.extend(_render_status(status))
    return lines


def _fetch_stock_snapshots(
    market: Market,
    symbols: list[str],
    fetch_stocks: Callable[[list[str]], list[RichStockData]],
) -> list[RichStockData]:
    try:
        return fetch_stocks(symbols)
    except Exception as exc:
        logger.warning('Batch %s signal snapshot fetch failed: %s', market, exc)
    stocks: list[RichStockData] = []
    for symbol in symbols:
        try:
            stocks.extend(fetch_stocks([symbol]))
        except Exception as exc:
            logger.warning(
                '%s signal snapshot fetch failed for %s: %s',
                market,
                symbol,
                exc,
            )
    return stocks


def _status_from_stock(
    symbol: str,
    market: Market,
    stock: RichStockData | None,
    history_count_90d: int,
) -> SignalStatus:
    if stock is None:
        return evaluate_signal_status(
            symbol=symbol,
            market=market,
            price=None,
            week52_high=None,
            ma50=None,
            history_count_90d=history_count_90d,
        )
    return evaluate_signal_status(
        symbol=symbol,
        market=market,
        price=stock.price,
        week52_high=stock.week52_high,
        ma50=stock.ma50,
        history_count_90d=history_count_90d,
    )


def _render_status(status: SignalStatus) -> list[str]:
    ma50_state = _ma50_state(status.ma50_broken)
    price = _format_optional_float(status.price)
    drop_pct = _format_optional_float(status.drop_pct, suffix='%')
    return [
        f'{_escape_md(status.symbol)}：{_escape_md(status.status)}',
        f'現價 `{price}`  距高點 `{drop_pct}`  MA50 {_escape_md(ma50_state)}',
        f'原因：{_escape_md(status.reason)}',
        _render_history_line(status),
        '',
    ]


def _render_history_line(status: SignalStatus) -> str:
    if status.history_count_90d <= 0:
        return f'近 90 天：{_escape_md(status.history_label)}'
    return (
        f'近 90 天：觸發 `{status.history_count_90d}` 次，'
        f'{_escape_md(status.history_label)}'
    )


def _ma50_state(value: bool | None) -> str:
    if value is None:
        return '未知'
    return '已跌破' if value else '未跌破'


def _format_optional_float(value: float | None, suffix: str = '') -> str:
    if value is None:
        return 'N/A'
    return f'{value:.2f}{suffix}'


def _history_label(count: int) -> HistoryLabel:
    if count <= 0:
        return '未觸發'
    if count == 1:
        return '短期訊號'
    return '訊號持續'


def _missing_data_reason(
    price: float | None,
    week52_high: float | None,
    ma50: float | None,
) -> str | None:
    if price is None or not math.isfinite(price) or price <= 0:
        return '缺少現價'
    if week52_high is None or not math.isfinite(week52_high) or week52_high <= 0:
        return '缺少 52 週高點'
    if ma50 is None or not math.isfinite(ma50) or ma50 <= 0:
        return '缺少 MA50'
    return None


def _classify_complete_data(
    market: Market,
    drop_pct: float,
    ma50_broken: bool,
) -> tuple[SignalState, str]:
    add_on_status = _add_on_status(market, drop_pct, ma50_broken)
    if add_on_status is not None:
        return add_on_status, f'回檔達{add_on_status[:2]}門檻，趨勢條件成立'
    if ma50_broken:
        return '觀察', '趨勢條件成立，但回檔未達加碼門檻'
    if -20.0 < drop_pct <= -15.0:
        return '觀察', '回檔接近加碼門檻'
    if drop_pct > -15.0:
        return '不加碼', '回檔未達門檻'
    return '不加碼', 'MA50 條件未成立'


def _add_on_status(
    market: Market,
    drop_pct: float,
    ma50_broken: bool,
) -> SignalState | None:
    if not ma50_broken:
        return None
    thresholds: tuple[tuple[float, SignalState], ...]
    if market == 'TW':
        thresholds = ((-30.0, '深度加碼'), (-25.0, '中度加碼'), (-20.0, '輕度加碼'))
    else:
        thresholds = ((-40.0, '深度加碼'), (-30.0, '中度加碼'), (-20.0, '輕度加碼'))
    for threshold, status in thresholds:
        if drop_pct <= threshold:
            return status
    return None
