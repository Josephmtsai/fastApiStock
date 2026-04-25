"""Integration tests for ``run_report_pipeline``.

These tests use the in-memory SQLite ``db_session`` fixture (so Postgres
upserts actually hit a real DB) plus mocked Telegram + sheet_writer + price
fetchers.  They verify the cron-style end-to-end happy paths.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.repositories.report_history_repo import (
    list_summary_history,
    list_symbol_history,
)
from fastapistock.services.report_service import run_report_pipeline

_RS = 'fastapistock.services.report_service'
_TZ = ZoneInfo('Asia/Taipei')


class _FakePrice:
    """Minimal stand-in matching the duck-typed ``RichStockData.price`` use."""

    def __init__(self, price: float) -> None:
        self.price = price


def _common_patches(
    *,
    portfolio_tw: dict[str, PortfolioEntry] | None = None,
    portfolio_us: dict[str, PortfolioEntry] | None = None,
) -> list[Any]:
    """Yield a chain of context-manager patches for both cron paths."""
    return [
        patch(f'{_RS}.portfolio_repo.fetch_pnl_tw', return_value=523456.0),
        patch(f'{_RS}.portfolio_repo.fetch_pnl_us', return_value=8345.0),
        patch(
            f'{_RS}.portfolio_repo.fetch_portfolio',
            return_value=portfolio_tw or {},
        ),
        patch(
            f'{_RS}.portfolio_repo.fetch_portfolio_us',
            return_value=portfolio_us or {},
        ),
        patch(f'{_RS}.portfolio_snapshot_repo.get_weekly', return_value=None),
        patch(f'{_RS}.portfolio_snapshot_repo.get_monthly', return_value=None),
        patch(f'{_RS}.portfolio_snapshot_repo.save_weekly'),
        patch(f'{_RS}.portfolio_snapshot_repo.save_monthly'),
        patch(f'{_RS}.signal_history_repo.list_signals', return_value=[]),
        patch(f'{_RS}.transactions_repo.sum_buy_amount', return_value=85000.0),
        patch(
            'fastapistock.services.stock_service.get_rich_tw_stocks',
            return_value=[_FakePrice(820.0)],
        ),
        patch(
            'fastapistock.services.us_stock_service.get_us_stocks',
            return_value=[_FakePrice(175.0)],
        ),
    ]


def test_weekly_cron_writes_postgres_and_calls_telegram(
    db_session: Session,
) -> None:
    """Weekly cron path: Postgres rows persisted + Telegram mock called once."""
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    portfolio_tw = {
        '2330': PortfolioEntry(
            symbol='2330', shares=100, avg_cost=750.5, unrealized_pnl=12345.0
        )
    }
    patches = _common_patches(portfolio_tw=portfolio_tw)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8],
        patches[9],
        patches[10],
        patches[11],
        patch(f'{_RS}._send_markdown', return_value=True) as mock_tg,
        patch(
            f'{_RS}.sheet_writer.append_monthly_history', return_value=True
        ) as mock_sheet,
    ):
        result = run_report_pipeline(report_type='weekly', trigger='cron', now=now)

    assert result.postgres_ok is True
    assert result.telegram_sent is True
    assert result.sheet_ok is None  # weekly path
    mock_tg.assert_called_once()
    mock_sheet.assert_not_called()  # weekly: never touch the sheet

    # Postgres should now contain one TW row plus a summary row.
    rows = list_symbol_history(symbol='2330', market='TW', report_type='weekly')
    assert len(rows) == 1
    assert rows[0].current_price == Decimal('820.0000')
    summaries = list_summary_history(report_type='weekly')
    assert len(summaries) == 1
    assert summaries[0].pnl_tw_total == Decimal('523456.00')


def test_monthly_cron_calls_sheet_writer_for_both_markets(
    db_session: Session,
) -> None:
    """Monthly path must call sheet_writer.append_monthly_history twice."""
    now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
    portfolio_tw = {
        '2330': PortfolioEntry(
            symbol='2330', shares=100, avg_cost=750.5, unrealized_pnl=12345.0
        )
    }
    portfolio_us = {
        'AAPL': PortfolioEntry(
            symbol='AAPL', shares=10, avg_cost=150.0, unrealized_pnl=250.0
        )
    }
    patches = _common_patches(portfolio_tw=portfolio_tw, portfolio_us=portfolio_us)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8],
        patches[9],
        patches[10],
        patches[11],
        patch(f'{_RS}._send_markdown', return_value=True),
        patch(
            f'{_RS}.sheet_writer.append_monthly_history', return_value=True
        ) as mock_sheet,
    ):
        result = run_report_pipeline(report_type='monthly', trigger='cron', now=now)

    assert result.postgres_ok is True
    assert result.sheet_ok is True
    # TW + US → exactly two calls
    assert mock_sheet.call_count == 2
    market_args = {call.args[0] for call in mock_sheet.call_args_list}
    assert market_args == {'TW', 'US'}

    rows_tw = list_symbol_history(symbol='2330', market='TW', report_type='monthly')
    rows_us = list_symbol_history(symbol='AAPL', market='US', report_type='monthly')
    assert len(rows_tw) == 1
    assert len(rows_us) == 1
