"""Unit tests for chart_service (spec-018 T2).

Only structural assertions are made (PNG magic number, no exception); no
pixel comparison. Rendering uses the Agg OO API so no GUI or network is
involved.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
)
from fastapistock.services import chart_service

_TZ = ZoneInfo('Asia/Taipei')
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def _snapshot(
    *,
    period: str,
    avg_cost: Decimal | None = Decimal('700'),
    pnl_pct: Decimal | None = Decimal('14.29'),
) -> SymbolSnapshot:
    return SymbolSnapshot(
        report_type='monthly',
        report_period=period,
        market='TW',
        symbol='2330',
        shares=Decimal('1000'),
        # E3 runtime-None defence: field is typed Decimal upstream.
        avg_cost=avg_cost,  # type: ignore[arg-type]
        current_price=Decimal('800'),
        market_value=Decimal('800000'),
        unrealized_pnl=Decimal('100000'),
        pnl_pct=pnl_pct,
        pnl_delta=None,
        captured_at=datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


def _summary(*, period: str) -> ReportSummary:
    return ReportSummary(
        report_type='monthly',
        report_period=period,
        pnl_tw_total=Decimal('500000'),
        pnl_us_total=Decimal('8000'),
        pnl_tw_delta=None,
        pnl_us_delta=None,
        buy_amount_twd=None,
        signals_count=0,
        symbols_count=3,
        captured_at=datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


class TestRenderSymbolChart:
    def test_returns_png_bytes(self) -> None:
        rows = [_snapshot(period='2026-02'), _snapshot(period='2026-03')]
        png = chart_service.render_symbol_chart(rows)
        assert png.startswith(_PNG_MAGIC)
        assert len(png) > 0

    def test_empty_rows_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            chart_service.render_symbol_chart([])

    def test_single_data_point_renders(self) -> None:
        # E2: marker='o' keeps a lone point visible.
        png = chart_service.render_symbol_chart([_snapshot(period='2026-03')])
        assert png.startswith(_PNG_MAGIC)

    def test_avg_cost_all_none_skips_dashed_line(self) -> None:
        # E3: defensive runtime-None avg_cost — solid line only, no error.
        rows = [
            _snapshot(period='2026-02', avg_cost=None),
            _snapshot(period='2026-03', avg_cost=None),
        ]
        png = chart_service.render_symbol_chart(rows)
        assert png.startswith(_PNG_MAGIC)

    def test_last_pnl_pct_none_skips_annotation(self) -> None:
        # E4: annotation is omitted, chart still renders.
        rows = [
            _snapshot(period='2026-02'),
            _snapshot(period='2026-03', pnl_pct=None),
        ]
        png = chart_service.render_symbol_chart(rows)
        assert png.startswith(_PNG_MAGIC)


class TestRenderSummaryChart:
    def test_all_market_dual_axis_returns_png(self) -> None:
        rows = [_summary(period='2026-02'), _summary(period='2026-03')]
        png = chart_service.render_summary_chart(rows, market='ALL')
        assert png.startswith(_PNG_MAGIC)

    def test_default_market_is_all(self) -> None:
        png = chart_service.render_summary_chart([_summary(period='2026-03')])
        assert png.startswith(_PNG_MAGIC)

    @pytest.mark.parametrize('market', ['TW', 'US'])
    def test_single_market_returns_png(self, market: str) -> None:
        rows = [_summary(period='2026-02'), _summary(period='2026-03')]
        png = chart_service.render_summary_chart(rows, market=market)
        assert png.startswith(_PNG_MAGIC)

    def test_empty_summaries_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            chart_service.render_summary_chart([])

    def test_unknown_market_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            chart_service.render_summary_chart(
                [_summary(period='2026-03')], market='EU'
            )

    def test_single_period_summary_renders(self) -> None:
        # E5: one point per line, still a valid PNG.
        png = chart_service.render_summary_chart(
            [_summary(period='2026-03')], market='ALL'
        )
        assert png.startswith(_PNG_MAGIC)
