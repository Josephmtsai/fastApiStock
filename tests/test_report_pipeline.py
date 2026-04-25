"""Unit tests for ``run_report_pipeline`` (spec-006 Phase 3).

These tests mock every external collaborator (Telegram / Postgres / Sheet /
fetch helpers) so they exercise pipeline orchestration without touching IO.
The integration coverage lives in :mod:`tests.test_report_pipeline_integration`.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from fastapistock.repositories.portfolio_repo import PortfolioEntry
from fastapistock.repositories.portfolio_snapshot_repo import PortfolioSnapshot
from fastapistock.services.report_service import (
    RunReportResult,
    run_report_pipeline,
)

_RS = 'fastapistock.services.report_service'
_TZ = ZoneInfo('Asia/Taipei')


@dataclass
class _FakePrice:
    """Stand-in for the rich-stock service result used by current-price lookup."""

    price: float


def _portfolio(*, market: str = 'TW') -> dict[str, PortfolioEntry]:
    return {
        '2330' if market == 'TW' else 'AAPL': PortfolioEntry(
            symbol='2330' if market == 'TW' else 'AAPL',
            shares=100,
            avg_cost=750.5,
            unrealized_pnl=12345.0,
        ),
    }


def _patch_pipeline_deps(
    *,
    pnl_tw: float | None = 523456.0,
    pnl_us: float | None = 8345.0,
    portfolio_tw: dict[str, PortfolioEntry] | None = None,
    portfolio_us: dict[str, PortfolioEntry] | None = None,
    prev_snapshot: PortfolioSnapshot | None = None,
    tw_price: float = 820.0,
    us_price: float = 175.0,
    upsert_symbol_side_effect: Exception | None = None,
    sheet_tw_ok: bool = True,
    sheet_us_ok: bool = True,
    telegram_ok: bool = True,
) -> ExitStack:
    """Patch every external collaborator the pipeline reaches.

    Returns an ExitStack the caller enters in a ``with`` block; individual
    mocks are pushed as attributes on the stack via :py:meth:`enter_context`.
    """
    stack = ExitStack()

    stack.enter_context(
        patch(f'{_RS}.portfolio_repo.fetch_pnl_tw', return_value=pnl_tw)
    )
    stack.enter_context(
        patch(f'{_RS}.portfolio_repo.fetch_pnl_us', return_value=pnl_us)
    )
    stack.enter_context(
        patch(
            f'{_RS}.portfolio_repo.fetch_portfolio',
            return_value=portfolio_tw if portfolio_tw is not None else {},
        )
    )
    stack.enter_context(
        patch(
            f'{_RS}.portfolio_repo.fetch_portfolio_us',
            return_value=portfolio_us if portfolio_us is not None else {},
        )
    )
    stack.enter_context(
        patch(
            f'{_RS}.portfolio_snapshot_repo.get_weekly',
            return_value=prev_snapshot,
        )
    )
    stack.enter_context(
        patch(
            f'{_RS}.portfolio_snapshot_repo.get_monthly',
            return_value=prev_snapshot,
        )
    )
    stack.enter_context(patch(f'{_RS}.portfolio_snapshot_repo.save_weekly'))
    stack.enter_context(patch(f'{_RS}.portfolio_snapshot_repo.save_monthly'))
    stack.enter_context(
        patch(f'{_RS}.signal_history_repo.list_signals', return_value=[])
    )
    stack.enter_context(
        patch(f'{_RS}.transactions_repo.sum_buy_amount', return_value=85000.0)
    )

    # Stock-service current_price lookup helpers (lazy-imported inside fn).
    stack.enter_context(
        patch(
            'fastapistock.services.stock_service.get_rich_tw_stocks',
            return_value=[_FakePrice(price=tw_price)],
        )
    )
    stack.enter_context(
        patch(
            'fastapistock.services.us_stock_service.get_us_stocks',
            return_value=[_FakePrice(price=us_price)],
        )
    )

    upsert_symbol_mock = stack.enter_context(
        patch(f'{_RS}.report_history_repo.upsert_symbol_snapshots')
    )
    if upsert_symbol_side_effect is not None:
        upsert_symbol_mock.side_effect = upsert_symbol_side_effect
    else:
        upsert_symbol_mock.side_effect = lambda rows: len(rows)
    upsert_summary_mock = stack.enter_context(
        patch(f'{_RS}.report_history_repo.upsert_report_summary')
    )

    sheet_mock = stack.enter_context(
        patch(
            f'{_RS}.sheet_writer.append_monthly_history',
            side_effect=lambda market, rows: (
                sheet_tw_ok if market == 'TW' else sheet_us_ok
            ),
        )
    )
    telegram_mock = stack.enter_context(
        patch(f'{_RS}._send_markdown', return_value=telegram_ok)
    )

    stack.upsert_symbol_mock = upsert_symbol_mock  # type: ignore[attr-defined]
    stack.upsert_summary_mock = upsert_summary_mock  # type: ignore[attr-defined]
    stack.sheet_mock = sheet_mock  # type: ignore[attr-defined]
    stack.telegram_mock = telegram_mock  # type: ignore[attr-defined]
    return stack


# ── Test cases ────────────────────────────────────────────────────────────


def test_dry_run_skips_every_side_effect() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps() as stack:
        result = run_report_pipeline(
            report_type='weekly',
            dry_run=True,
            now=now,
        )

    assert result.dry_run is True
    assert result.telegram_sent is False
    assert result.postgres_ok is False
    assert result.sheet_ok is None
    assert result.symbol_rows_written == 0
    assert result.summary_written is False
    assert result.errors == []
    stack.telegram_mock.assert_not_called()  # type: ignore[attr-defined]
    stack.upsert_symbol_mock.assert_not_called()  # type: ignore[attr-defined]
    stack.sheet_mock.assert_not_called()  # type: ignore[attr-defined]


def test_skip_telegram_still_runs_postgres() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps() as stack:
        result = run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    stack.telegram_mock.assert_not_called()  # type: ignore[attr-defined]
    stack.upsert_symbol_mock.assert_called_once()  # type: ignore[attr-defined]
    assert result.telegram_sent is False
    assert result.postgres_ok is True


def test_postgres_failure_does_not_block_sheet_step() -> None:
    from sqlalchemy.exc import SQLAlchemyError

    now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps(
        portfolio_tw=_portfolio(market='TW'),
        upsert_symbol_side_effect=SQLAlchemyError('db down'),
    ) as stack:
        result = run_report_pipeline(
            report_type='monthly',
            skip_telegram=True,
            now=now,
        )
    assert result.postgres_ok is False
    assert 'SQLAlchemyError' in result.errors
    # Sheet step still ran (monthly + skip_sheet=False)
    assert stack.sheet_mock.call_count == 2  # type: ignore[attr-defined]


def test_weekly_report_sheet_ok_is_none() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps() as stack:
        result = run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    assert result.sheet_ok is None
    stack.sheet_mock.assert_not_called()  # type: ignore[attr-defined]


def test_telegram_failure_does_not_block_other_steps() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps(telegram_ok=False) as stack:
        result = run_report_pipeline(
            report_type='weekly',
            now=now,
        )
    assert result.telegram_sent is False
    assert result.postgres_ok is True
    stack.upsert_symbol_mock.assert_called_once()  # type: ignore[attr-defined]


def test_report_period_none_weekly_auto_fills_sunday() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)  # already a Sunday
    with _patch_pipeline_deps():
        result = run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    # Most recent Sunday on/before 2026-04-26 is 2026-04-26.
    assert result.report_period == '2026-04-26'


def test_report_period_explicit_monthly_uses_override() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps():
        result = run_report_pipeline(
            report_type='monthly',
            report_period='2026-03',
            skip_telegram=True,
            skip_sheet=True,
            now=now,
        )
    assert result.report_period == '2026-03'


def test_report_period_bad_format_raises_value_error() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps(), pytest.raises(ValueError):
        run_report_pipeline(
            report_type='monthly',
            report_period='bad-format',
            skip_telegram=True,
            skip_sheet=True,
            now=now,
        )


def test_errors_empty_list_on_happy_path() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps():
        result = run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    assert result.errors == []


def test_logger_adapter_injects_job_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    caplog.set_level(logging.INFO, logger='fastapistock.report_history')
    with _patch_pipeline_deps():
        result = run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    start_records = [
        r for r in caplog.records if r.message == 'report_history.build.start'
    ]
    assert start_records, 'expected report_history.build.start log'
    record_extra = getattr(start_records[0], 'job_id', None)
    assert record_extra == result.job_id


def test_decimal_boundary_float_zero_one_round_trips_via_str() -> None:
    """``Decimal(str(0.1))`` must equal ``Decimal('0.1')`` (no float drift)."""
    captured: dict[str, Any] = {}

    def _capture(rows: list[Any]) -> int:
        captured['rows'] = rows
        return len(rows)

    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps(
        portfolio_tw={
            '2330': PortfolioEntry(
                symbol='2330',
                shares=10,
                avg_cost=0.1,  # the float we want to preserve as Decimal('0.1')
                unrealized_pnl=0.0,
            )
        },
        tw_price=0.1,
    ) as stack:
        stack.upsert_symbol_mock.side_effect = _capture  # type: ignore[attr-defined]
        run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    rows = captured.get('rows', [])
    assert rows, 'expected at least one snapshot row'
    row = rows[0]
    assert row.avg_cost == Decimal('0.1')
    assert row.current_price == Decimal('0.1')


def test_trigger_backfill_propagates_into_log_extra(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    caplog.set_level(logging.INFO, logger='fastapistock.report_history')
    with _patch_pipeline_deps():
        run_report_pipeline(
            report_type='weekly',
            trigger='backfill',
            skip_telegram=True,
            now=now,
        )
    starts = [r for r in caplog.records if r.message == 'report_history.build.start']
    assert starts and starts[0].trigger == 'backfill'


def test_pnl_fetch_failure_skips_summary_and_records_error() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps(pnl_tw=None) as stack:
        result = run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    assert result.summary_written is False
    assert 'pnl_fetch_failed' in result.errors
    stack.upsert_summary_mock.assert_not_called()  # type: ignore[attr-defined]


def test_returns_run_report_result_dataclass() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps():
        result = run_report_pipeline(
            report_type='weekly',
            skip_telegram=True,
            now=now,
        )
    assert isinstance(result, RunReportResult)
    assert result.job_id and len(result.job_id) == 8
    assert result.duration_ms >= 0


def test_sheet_failure_returns_false_not_none() -> None:
    now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
    with _patch_pipeline_deps(
        portfolio_tw=_portfolio(market='TW'),
        sheet_tw_ok=False,
    ):
        result = run_report_pipeline(
            report_type='monthly',
            skip_telegram=True,
            now=now,
        )
    assert result.sheet_ok is False
