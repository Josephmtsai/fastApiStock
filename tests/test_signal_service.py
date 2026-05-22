"""Tests for Telegram /signal classification and overview rendering."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import pytest

from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.repositories.signal_history_repo import SignalRecord
from fastapistock.schemas.stock import RichStockData
from fastapistock.services.signal_service import (
    build_signal_overview,
    evaluate_signal_status,
)

_TZ = ZoneInfo('Asia/Taipei')
_Market = Literal['TW', 'US']


def _make_rich_stock(
    symbol: str,
    market: _Market,
    price: float,
    week52_high: float | None,
    ma50: float | None,
) -> RichStockData:
    return RichStockData(
        symbol=symbol,
        display_name=f'{symbol} Corp',
        market=market,
        price=price,
        prev_close=price - 1.0,
        change=1.0,
        change_pct=1.0,
        ma20=price,
        ma50=ma50,
        volume=1000,
        volume_avg20=900,
        week52_high=week52_high,
        week52_low=price - 10.0,
    )


@pytest.mark.parametrize(
    ('market', 'price', 'expected'),
    [
        ('TW', 69.0, '深度加碼'),
        ('TW', 74.0, '中度加碼'),
        ('TW', 80.0, '輕度加碼'),
        ('US', 59.0, '深度加碼'),
    ],
)
def test_evaluate_signal_status_classifies_add_on_thresholds(
    market: _Market,
    price: float,
    expected: str,
) -> None:
    status = evaluate_signal_status(
        symbol='TEST',
        market=market,
        price=price,
        week52_high=100.0,
        ma50=90.0,
        history_count_90d=0,
    )

    assert status.status == expected


def test_evaluate_signal_status_observes_when_price_below_ma50() -> None:
    status = evaluate_signal_status(
        symbol='TEST',
        market='TW',
        price=84.0,
        week52_high=100.0,
        ma50=90.0,
        history_count_90d=0,
    )

    assert status.status == '觀察'
    assert status.ma50_broken is True


def test_evaluate_signal_status_returns_not_add_when_conditions_not_met() -> None:
    status = evaluate_signal_status(
        symbol='TEST',
        market='TW',
        price=90.0,
        week52_high=100.0,
        ma50=80.0,
        history_count_90d=0,
    )

    assert status.status == '不加碼'
    assert '回檔未達門檻' in status.reason


@pytest.mark.parametrize(
    ('price', 'week52_high', 'ma50', 'expected_reason'),
    [
        (None, 100.0, 90.0, '缺少現價'),
        (80.0, None, 90.0, '缺少 52 週高點'),
        (80.0, 100.0, None, '缺少 MA50'),
        (80.0, 0.0, 90.0, '缺少 52 週高點'),
    ],
)
def test_evaluate_signal_status_marks_data_insufficient(
    price: float | None,
    week52_high: float | None,
    ma50: float | None,
    expected_reason: str,
) -> None:
    status = evaluate_signal_status(
        symbol='TEST',
        market='TW',
        price=price,
        week52_high=week52_high,
        ma50=ma50,
        history_count_90d=0,
    )

    assert status.status == '資料不足'
    assert expected_reason in status.reason


def test_build_signal_overview_renders_all_holdings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 21, 9, 30, tzinfo=_TZ)
    tw_entry = PortfolioEntry('2330', shares=1000, avg_cost=700.0, unrealized_pnl=1.0)
    us_entry = PortfolioEntry('AAPL', shares=10, avg_cost=180.0, unrealized_pnl=2.0)
    tw_stock = _make_rich_stock('2330', 'TW', 80.0, 100.0, 90.0)
    us_stock = _make_rich_stock('AAPL', 'US', 90.0, 100.0, 80.0)
    records = [
        SignalRecord('2330', 'TW', 1, -20.0, 80.0, 100.0, 90.0, now),
        SignalRecord('2330', 'TW', 2, -25.0, 74.0, 100.0, 90.0, now),
        SignalRecord('AAPL', 'US', 1, -20.0, 80.0, 100.0, 90.0, now),
    ]

    monkeypatch.setattr(
        'fastapistock.services.signal_service.portfolio_repo.fetch_portfolio',
        lambda: {'2330': tw_entry},
    )
    monkeypatch.setattr(
        'fastapistock.services.signal_service.portfolio_repo.fetch_portfolio_us',
        lambda: {'AAPL': us_entry},
    )
    monkeypatch.setattr(
        'fastapistock.services.signal_service.stock_service.get_rich_tw_stocks',
        lambda symbols: [tw_stock],
    )
    monkeypatch.setattr(
        'fastapistock.services.signal_service.us_stock_service.get_us_stocks',
        lambda symbols: [us_stock],
    )
    monkeypatch.setattr(
        'fastapistock.services.signal_service.signal_history_repo.list_signals',
        lambda start_date, end_date: records,
    )

    output = build_signal_overview(now)

    assert '加碼訊號總覽' in output
    assert '台股' in output
    assert '美股' in output
    assert '2330' in output
    assert 'AAPL' in output
    assert '現價' in output
    assert '距高點' in output
    assert 'MA50' in output
    assert '原因' in output
    assert '近 90 天' in output
    assert '訊號持續' in output
    assert '短期訊號' in output
    for banned in ('建議金額', '買進股數', '預算', '剩餘', '賣出'):
        assert banned not in output


def test_build_signal_overview_marks_one_failed_symbol_data_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 21, 9, 30, tzinfo=_TZ)
    good_entry = PortfolioEntry('2330', shares=1000, avg_cost=700.0, unrealized_pnl=1.0)
    bad_entry = PortfolioEntry('9999', shares=1000, avg_cost=50.0, unrealized_pnl=0.0)
    good_stock = _make_rich_stock('2330', 'TW', 80.0, 100.0, 90.0)

    def fake_fetch_tw_stocks(symbols: list[str]) -> list[RichStockData]:
        if '9999' in symbols:
            raise ValueError('bad symbol')
        return [good_stock]

    monkeypatch.setattr(
        'fastapistock.services.signal_service.portfolio_repo.fetch_portfolio',
        lambda: {'2330': good_entry, '9999': bad_entry},
    )
    monkeypatch.setattr(
        'fastapistock.services.signal_service.portfolio_repo.fetch_portfolio_us',
        lambda: {},
    )
    monkeypatch.setattr(
        'fastapistock.services.signal_service.stock_service.get_rich_tw_stocks',
        fake_fetch_tw_stocks,
    )
    monkeypatch.setattr(
        'fastapistock.services.signal_service.signal_history_repo.list_signals',
        lambda start_date, end_date: [],
    )

    output = build_signal_overview(now)

    assert '資料讀取失敗' not in output
    assert '2330' in output
    assert '9999' in output
    assert '9999：資料不足' in output
