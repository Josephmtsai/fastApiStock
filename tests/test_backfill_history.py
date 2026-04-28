"""Tests for fastapistock.scripts.backfill_history and related repo additions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from fastapistock.repositories.transactions_repo import (
    Transaction,
    USTransaction,
    fetch_us_transactions,
    get_earliest_transaction_month,
)
from fastapistock.scripts.backfill_history import (
    _backfill_month,
    _fetch_close_price,
    _repair_deltas,
)

_TZ = ZoneInfo('Asia/Taipei')
_MOD_CFG = 'fastapistock.repositories.transactions_repo.config'
_PATCH_SHEETS_ID = f'{_MOD_CFG}.GOOGLE_SHEETS_ID'
_PATCH_US_GID = f'{_MOD_CFG}.GOOGLE_SHEETS_US_TRANSACTIONS_GID'
_PATCH_TW_GID = f'{_MOD_CFG}.GOOGLE_SHEETS_TW_TRANSACTIONS_GID'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _us_tx(
    symbol: str = 'AAPL',
    d: date = date(2024, 3, 15),
    action: str = 'Buy',
    price: float = 180.0,
    shares: float = 10.0,
    net_cash_flow: float = -1800.0,
    current_stock_price: float = 185.0,
) -> USTransaction:
    return USTransaction(
        symbol=symbol,
        date=d,
        action=action,
        price=price,
        shares=shares,
        net_cash_flow=net_cash_flow,
        current_stock_price=current_stock_price,
    )


def _tw_tx(
    symbol: str = '2330',
    d: date = date(2024, 3, 15),
    action: str = '買',
    shares: float = 1000.0,
    cost: float = 820.0,
    net_shares: float = 1000.0,
    net_amount: float = -820000.0,
    year: int = 2024,
) -> Transaction:
    return Transaction(
        symbol=symbol,
        date=d,
        shares=shares,
        cost=cost,
        action=action,
        net_shares=net_shares,
        net_amount=net_amount,
        year=year,
    )


def _mock_http_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Test 1: fetch_us_transactions empty when unconfigured
# ---------------------------------------------------------------------------


def test_fetch_us_transactions_empty_when_unconfigured() -> None:
    with patch(_PATCH_SHEETS_ID, ''), patch(_PATCH_US_GID, '456'):
        result = fetch_us_transactions()
    assert result == []


def test_fetch_us_transactions_empty_when_gid_missing() -> None:
    with patch(_PATCH_SHEETS_ID, 'abc'), patch(_PATCH_US_GID, ''):
        result = fetch_us_transactions()
    assert result == []


# ---------------------------------------------------------------------------
# Test 2: fetch_us_transactions parses rows + skips malformed
# ---------------------------------------------------------------------------


def test_fetch_us_transactions_parses_rows() -> None:
    csv_text = (
        'Date,Ticker,Action Type,Price,Shares,Net Cash Flow,Current Stock Price\n'
        '2024-03-15,AAPL,Buy,180.0,10,"-1800.0",185.0\n'
        '2024-04-01,MSFT,Sell,420.0,5,2100.0,415.0\n'
        'bad,row\n'  # malformed: too few columns
    )
    with (
        patch(_PATCH_SHEETS_ID, '123'),
        patch(_PATCH_US_GID, '456'),
        patch('httpx.get', return_value=_mock_http_response(csv_text)),
    ):
        result = fetch_us_transactions()

    assert len(result) == 2

    aapl = result[0]
    assert aapl.symbol == 'AAPL'
    assert aapl.date == date(2024, 3, 15)
    assert aapl.action == 'Buy'
    assert aapl.price == 180.0
    assert aapl.shares == 10.0
    assert aapl.net_cash_flow == -1800.0
    assert aapl.current_stock_price == 185.0

    msft = result[1]
    assert msft.symbol == 'MSFT'
    assert msft.action == 'Sell'
    assert msft.price == 420.0


# ---------------------------------------------------------------------------
# Test 3: get_earliest_transaction_month TW returns min date
# ---------------------------------------------------------------------------


def test_get_earliest_transaction_month_tw_returns_min_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    txns = [
        _tw_tx(d=date(2024, 3, 15)),
        _tw_tx(d=date(2023, 6, 1)),
    ]
    monkeypatch.setattr(
        'fastapistock.repositories.transactions_repo.fetch_tw_transactions',
        lambda: txns,
    )
    result = get_earliest_transaction_month('TW')
    assert result == (2023, 6)


# ---------------------------------------------------------------------------
# Test 4: get_earliest_transaction_month US returns min date
# ---------------------------------------------------------------------------


def test_get_earliest_transaction_month_us_returns_min_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    txns = [
        _us_tx(d=date(2022, 11, 5)),
        _us_tx(d=date(2021, 8, 20)),
    ]
    monkeypatch.setattr(
        'fastapistock.repositories.transactions_repo.fetch_us_transactions',
        lambda: txns,
    )
    result = get_earliest_transaction_month('US')
    assert result == (2021, 8)


# ---------------------------------------------------------------------------
# Test 5: get_earliest_transaction_month empty returns None
# ---------------------------------------------------------------------------


def test_get_earliest_transaction_month_empty_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'fastapistock.repositories.transactions_repo.fetch_tw_transactions',
        lambda: [],
    )
    result = get_earliest_transaction_month('TW')
    assert result is None


# ---------------------------------------------------------------------------
# Test 6: get_earliest_transaction_month uses Redis cache (second call)
# ---------------------------------------------------------------------------


def test_get_earliest_transaction_month_uses_redis_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call should use Redis cache and not call fetch_tw_transactions again."""
    call_count = {'n': 0}

    def _fetch() -> list[Transaction]:
        call_count['n'] += 1
        return [_tw_tx(d=date(2023, 5, 10))]

    monkeypatch.setattr(
        'fastapistock.repositories.transactions_repo.fetch_tw_transactions',
        _fetch,
    )

    # First call populates cache
    result1 = get_earliest_transaction_month('TW')
    assert result1 == (2023, 5)
    assert call_count['n'] == 1

    # Second call should hit Redis (autouse fixture injects fakeredis)
    result2 = get_earliest_transaction_month('TW')
    assert result2 == (2023, 5)
    assert call_count['n'] == 1  # fetch not called again


# ---------------------------------------------------------------------------
# Test 7: _fetch_close_price returns first valid close
# ---------------------------------------------------------------------------


def test_fetch_close_price_returns_first_valid_close() -> None:
    import pandas as pd

    mock_hist = pd.DataFrame({'Close': [150.0, 151.0]})

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    with patch('yfinance.Ticker', return_value=mock_ticker):
        result = _fetch_close_price('AAPL', date(2025, 6, 30))

    assert result == 150.0
    mock_ticker.history.assert_called_once()


def test_fetch_close_price_returns_none_on_empty() -> None:
    import pandas as pd

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame({'Close': []})

    with patch('yfinance.Ticker', return_value=mock_ticker):
        result = _fetch_close_price('AAPL', date(2025, 6, 30))

    assert result is None


# ---------------------------------------------------------------------------
# Test 8: _backfill_month TW upsert called
# ---------------------------------------------------------------------------


def test_backfill_month_tw_upsert_called(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    """Two buy transactions for same symbol → upsert_symbol_snapshots is called."""
    import pandas as pd

    txns = [
        _tw_tx(
            symbol='2330',
            d=date(2025, 6, 1),
            action='買',
            net_shares=1000.0,
            net_amount=-820000.0,
        ),
        _tw_tx(
            symbol='2330',
            d=date(2025, 6, 15),
            action='買',
            net_shares=500.0,
            net_amount=-415000.0,
        ),
    ]

    monkeypatch.setattr(
        'fastapistock.scripts.backfill_history.fetch_tw_transactions',
        lambda: txns,
    )
    monkeypatch.setattr(
        'fastapistock.scripts.backfill_history.fetch_us_transactions',
        lambda: [],
    )

    mock_hist = pd.DataFrame({'Close': [900.0]})
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    upsert_snapshots_calls: list[list[object]] = []
    original_upsert_snapshots = (
        'fastapistock.scripts.backfill_history.upsert_symbol_snapshots'
    )

    def _fake_upsert_snapshots(rows: list[object]) -> int:
        upsert_snapshots_calls.append(rows)
        return len(rows)

    monkeypatch.setattr(
        original_upsert_snapshots,
        _fake_upsert_snapshots,
    )
    monkeypatch.setattr(
        'fastapistock.scripts.backfill_history.upsert_report_summary',
        lambda row: None,
    )
    monkeypatch.setattr(
        'fastapistock.scripts.backfill_history.sheet_writer.append_monthly_history',
        lambda market, rows: True,
    )
    monkeypatch.setattr(
        'fastapistock.scripts.backfill_history.transactions_repo.sum_buy_amount',
        lambda y, m: 0.0,
    )

    import time as _time_mod

    monkeypatch.setattr(_time_mod, 'sleep', lambda s: None)

    with patch('yfinance.Ticker', return_value=mock_ticker):
        new_tw, new_us, _, _ = _backfill_month(
            'TW',
            2025,
            6,
            dry_run=False,
            skip_sheet=True,
            filter_symbols=None,
            verbose=False,
        )

    assert len(upsert_snapshots_calls) == 1
    rows = upsert_snapshots_calls[0]
    assert len(rows) == 1

    snap = rows[0]
    assert hasattr(snap, 'symbol')
    assert snap.symbol == '2330'  # type: ignore[union-attr]
    assert snap.market == 'TW'  # type: ignore[union-attr]
    assert snap.report_period == '2025-06'  # type: ignore[union-attr]
    # 1000 + 500 = 1500 shares
    assert snap.shares == Decimal('1500.0')  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Test 9: _repair_deltas updates delta fields
# ---------------------------------------------------------------------------


def test_repair_deltas_updates_delta_fields(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    """Seed 3 summary rows, call _repair_deltas, verify delta values."""
    from fastapistock.repositories.report_history_repo import (
        ReportSummary,
        list_summary_history,
        upsert_report_summary,
    )

    cap = datetime(2025, 1, 31, 21, 0, tzinfo=_TZ)

    rows = [
        ReportSummary(
            report_type='monthly',
            report_period='2025-01',
            pnl_tw_total=Decimal('100000'),
            pnl_us_total=Decimal('5000'),
            pnl_tw_delta=None,
            pnl_us_delta=None,
            buy_amount_twd=None,
            signals_count=0,
            symbols_count=1,
            captured_at=cap,
        ),
        ReportSummary(
            report_type='monthly',
            report_period='2025-02',
            pnl_tw_total=Decimal('120000'),
            pnl_us_total=Decimal('6000'),
            pnl_tw_delta=None,
            pnl_us_delta=None,
            buy_amount_twd=None,
            signals_count=0,
            symbols_count=1,
            captured_at=cap,
        ),
        ReportSummary(
            report_type='monthly',
            report_period='2025-03',
            pnl_tw_total=Decimal('115000'),
            pnl_us_total=Decimal('7500'),
            pnl_tw_delta=None,
            pnl_us_delta=None,
            buy_amount_twd=None,
            signals_count=0,
            symbols_count=1,
            captured_at=cap,
        ),
    ]

    for row in rows:
        upsert_report_summary(row)

    _repair_deltas()

    results = list_summary_history(
        report_type='monthly',
        since=date(2025, 1, 1),
        until=date(2025, 12, 31),
        limit=100,
    )

    assert len(results) == 3

    # First row: both deltas None
    first = results[0]
    assert first.report_period == '2025-01'
    assert first.pnl_tw_delta is None
    assert first.pnl_us_delta is None

    # Second row: delta = 120000 - 100000 = 20000
    second = results[1]
    assert second.report_period == '2025-02'
    assert second.pnl_tw_delta == Decimal('20000')
    assert second.pnl_us_delta == Decimal('1000')

    # Third row: delta = 115000 - 120000 = -5000
    third = results[2]
    assert third.report_period == '2025-03'
    assert third.pnl_tw_delta == Decimal('-5000')
    assert third.pnl_us_delta == Decimal('1500')
