"""Unit tests for chart_service (spec-018 T2, spec-019 T3/T4).

spec-018 classes only assert structure (PNG magic number, no exception).
spec-019 classes capture the ``Figure`` through a ``_fig_to_png`` spy and
assert axis titles, tick formatter, value labels, the pnl text box and the
stacked ``'ALL'`` layout. No pixel comparison; Agg OO API only.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from matplotlib.figure import Figure
from matplotlib.ticker import StrMethodFormatter

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
    price: Decimal | None = Decimal('800'),
    market: str = 'TW',
    report_type: str = 'monthly',
) -> SymbolSnapshot:
    return SymbolSnapshot(
        report_type=report_type,
        report_period=period,
        market=market,
        symbol='2330',
        shares=Decimal('1000'),
        # E3/E5 runtime-None defence: fields are typed Decimal upstream.
        avg_cost=avg_cost,  # type: ignore[arg-type]
        current_price=price,  # type: ignore[arg-type]
        market_value=Decimal('800000'),
        unrealized_pnl=Decimal('100000'),
        pnl_pct=pnl_pct,
        pnl_delta=None,
        captured_at=datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


def _summary(
    *,
    period: str,
    tw: Decimal = Decimal('500000'),
    us: Decimal = Decimal('8000'),
    report_type: str = 'monthly',
) -> ReportSummary:
    return ReportSummary(
        report_type=report_type,
        report_period=period,
        pnl_tw_total=tw,
        pnl_us_total=us,
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


# ── spec-019: Figure/Axes structural assertions ────────────────────────────


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[Figure]:
    """Spy on ``_fig_to_png`` and collect every Figure it rasterizes."""
    figures: list[Figure] = []
    original: Callable[[Figure], bytes] = chart_service._fig_to_png

    def spy(fig: Figure) -> bytes:
        figures.append(fig)
        return original(fig)

    monkeypatch.setattr(chart_service, '_fig_to_png', spy)
    return figures


def _texts(fig: Figure, index: int = 0) -> list[str]:
    return [t.get_text() for t in fig.axes[index].texts]


def _pnl_texts(fig: Figure) -> list[str]:
    return [t for t in _texts(fig) if t.startswith('PnL ')]


def _legend_labels(fig: Figure, index: int = 0) -> list[str]:
    legend = fig.axes[index].get_legend()
    assert legend is not None
    return [t.get_text() for t in legend.get_texts()]


def _assert_y_grid_only(fig: Figure, index: int = 0) -> None:
    ax = fig.axes[index]
    assert ax.yaxis.get_gridlines()[0].get_visible() is True
    assert ax.xaxis.get_gridlines()[0].get_visible() is False


class TestSymbolChartLabels:
    """G1/G4 golden sample and E2–E7/E9 edge cases for render_symbol_chart."""

    def test_golden_sample_g1(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart(
            [_snapshot(period='2026-02'), _snapshot(period='2026-03')]
        )
        fig = captured[0]
        assert len(fig.axes) == 1
        assert tuple(fig.get_size_inches()) == (8.0, 4.5)
        ax = fig.axes[0]
        assert ax.get_title() == '2330 (TW) monthly'
        assert ax.get_xlabel() == 'Report period (monthly)'
        assert ax.get_ylabel() == 'Price (TWD)'
        assert _legend_labels(fig) == ['close', 'avg cost']
        fmt = ax.yaxis.get_major_formatter()
        assert isinstance(fmt, StrMethodFormatter)
        assert fmt(1234.5) == '1,234.50'
        assert Counter(_texts(fig)) == Counter(
            {'800.00': 2, '700.00': 1, 'PnL +14.29%': 1}
        )
        assert len(ax.get_lines()) == 2
        _assert_y_grid_only(fig)

    def test_pnl_box_is_axes_anchored_with_bbox(self, captured: list[Figure]) -> None:
        # AC-3.1: axes-fraction anchor so the box never gets clipped.
        chart_service.render_symbol_chart([_snapshot(period='2026-03')])
        ax = captured[0].axes[0]
        (box,) = [t for t in ax.texts if t.get_text().startswith('PnL ')]
        assert box.get_transform() == ax.transAxes
        assert box.get_position() == (0.98, 0.95)
        assert box.get_ha() == 'right'
        assert box.get_va() == 'top'
        assert box.get_bbox_patch() is not None

    def test_negative_pnl_pct_keeps_sign(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart(
            [_snapshot(period='2026-03', pnl_pct=Decimal('-3.5'))]
        )
        assert _pnl_texts(captured[0]) == ['PnL -3.50%']

    def test_weekly_labels_g4(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart(
            [_snapshot(period='2026-03-06', report_type='weekly')]
        )
        ax = captured[0].axes[0]
        assert ax.get_title() == '2330 (TW) weekly'
        assert ax.get_xlabel() == 'Report period (weekly)'

    def test_us_market_ylabel_is_usd(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart([_snapshot(period='2026-03', market='US')])
        assert captured[0].axes[0].get_ylabel() == 'Price (USD)'

    def test_unknown_market_ylabel_falls_back_e7(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart([_snapshot(period='2026-03', market='EU')])
        assert captured[0].axes[0].get_ylabel() == 'Price'

    def test_single_point_has_one_close_label_e2(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart([_snapshot(period='2026-03')])
        assert Counter(_texts(captured[0])) == Counter(
            {'800.00': 1, '700.00': 1, 'PnL +14.29%': 1}
        )

    def test_avg_cost_all_none_no_dashed_no_label_e3(
        self, captured: list[Figure]
    ) -> None:
        chart_service.render_symbol_chart(
            [
                _snapshot(period='2026-02', avg_cost=None),
                _snapshot(period='2026-03', avg_cost=None),
            ]
        )
        fig = captured[0]
        assert _legend_labels(fig) == ['close']
        assert len(fig.axes[0].get_lines()) == 1
        assert Counter(_texts(fig)) == Counter({'800.00': 2, 'PnL +14.29%': 1})

    def test_last_pnl_pct_none_has_no_box_e4(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart(
            [_snapshot(period='2026-02'), _snapshot(period='2026-03', pnl_pct=None)]
        )
        assert _pnl_texts(captured[0]) == []

    def test_last_close_nan_still_shows_pnl_box_e5(
        self, captured: list[Figure]
    ) -> None:
        # E5: box no longer depends on the last close coordinate; the NaN
        # point itself produces no value label.
        chart_service.render_symbol_chart(
            [_snapshot(period='2026-02'), _snapshot(period='2026-03', price=None)]
        )
        assert Counter(_texts(captured[0])) == Counter(
            {'800.00': 1, '700.00': 1, 'PnL +14.29%': 1}
        )

    def test_middle_nan_skips_that_label_e6(self, captured: list[Figure]) -> None:
        chart_service.render_symbol_chart(
            [
                _snapshot(period='2026-01'),
                _snapshot(period='2026-02', price=None),
                _snapshot(period='2026-03', price=Decimal('810')),
            ]
        )
        assert Counter(_texts(captured[0])) == Counter(
            {'800.00': 1, '810.00': 1, '700.00': 1, 'PnL +14.29%': 1}
        )

    def test_avg_cost_last_nan_not_labelled_e9(self, captured: list[Figure]) -> None:
        # E9: only_last looks at index -1 only; no fallback to earlier points.
        chart_service.render_symbol_chart(
            [_snapshot(period='2026-02'), _snapshot(period='2026-03', avg_cost=None)]
        )
        fig = captured[0]
        assert _legend_labels(fig) == ['close', 'avg cost']
        assert Counter(_texts(fig)) == Counter({'800.00': 2, 'PnL +14.29%': 1})


class TestSummaryChartLabels:
    """G2/G3/G4 golden samples and E2/E6/E12/E13 for render_summary_chart."""

    def test_golden_sample_g2_all_stacked(self, captured: list[Figure]) -> None:
        chart_service.render_summary_chart(
            [_summary(period='2026-02'), _summary(period='2026-03')], market='ALL'
        )
        fig = captured[0]
        axes = fig.axes
        assert len(axes) == 2
        assert tuple(fig.get_size_inches()) == (8.0, 6.5)
        assert axes[0].get_position().y0 > axes[1].get_position().y0
        assert axes[1].yaxis.get_ticks_position() == 'left'
        assert axes[0].get_shared_x_axes().joined(axes[0], axes[1])
        assert axes[0].get_title() == 'Account P&L (monthly)'
        assert axes[1].get_title() == ''
        assert axes[0].get_ylabel() == 'TW P&L (TWD)'
        assert axes[1].get_ylabel() == 'US P&L (USD)'
        assert axes[0].get_xlabel() == ''
        assert axes[1].get_xlabel() == 'Report period (monthly)'
        assert all(not t.get_visible() for t in axes[0].get_xticklabels())
        assert _legend_labels(fig, 0) == ['TW P&L (TWD)']
        assert _legend_labels(fig, 1) == ['US P&L (USD)']
        for index in (0, 1):
            fmt = axes[index].yaxis.get_major_formatter()
            assert isinstance(fmt, StrMethodFormatter)
            assert fmt(610000) == '610,000'
            assert len(axes[index].get_lines()) == 1
            _assert_y_grid_only(fig, index)
        assert _texts(fig, 0) == ['500,000', '500,000']
        assert _texts(fig, 1) == ['8,000', '8,000']

    def test_golden_sample_g3_single_tw(self, captured: list[Figure]) -> None:
        chart_service.render_summary_chart([_summary(period='2026-03')], market='TW')
        fig = captured[0]
        assert len(fig.axes) == 1
        assert tuple(fig.get_size_inches()) == (8.0, 4.5)
        ax = fig.axes[0]
        assert ax.get_title() == 'Account P&L (monthly)'
        assert ax.get_ylabel() == 'TW P&L (TWD)'
        assert ax.get_xlabel() == 'Report period (monthly)'
        assert _texts(fig) == ['500,000']
        assert _legend_labels(fig) == ['TW P&L (TWD)']
        _assert_y_grid_only(fig)

    def test_single_us_labels_us_values(self, captured: list[Figure]) -> None:
        chart_service.render_summary_chart(
            [_summary(period='2026-02'), _summary(period='2026-03')], market='US'
        )
        fig = captured[0]
        assert len(fig.axes) == 1
        assert _texts(fig) == ['8,000', '8,000']
        assert _legend_labels(fig) == ['US P&L (USD)']

    def test_weekly_title_and_xlabel_g4(self, captured: list[Figure]) -> None:
        chart_service.render_summary_chart(
            [_summary(period='2026-03-06', report_type='weekly')], market='ALL'
        )
        axes = captured[0].axes
        assert axes[0].get_title() == 'Account P&L (weekly)'
        assert axes[1].get_xlabel() == 'Report period (weekly)'

    def test_single_period_all_has_one_label_each_e2(
        self, captured: list[Figure]
    ) -> None:
        chart_service.render_summary_chart([_summary(period='2026-03')], market='ALL')
        fig = captured[0]
        assert _texts(fig, 0) == ['500,000']
        assert _texts(fig, 1) == ['8,000']

    def test_negative_pnl_label_keeps_minus_e12(self, captured: list[Figure]) -> None:
        chart_service.render_summary_chart(
            [_summary(period='2026-03', tw=Decimal('-12345'), us=Decimal('-0.4'))],
            market='ALL',
        )
        fig = captured[0]
        assert _texts(fig, 0) == ['-12,345']
        assert _texts(fig, 1) == ['-0']

    def test_constant_zero_series_labels_zero_e13(self, captured: list[Figure]) -> None:
        chart_service.render_summary_chart(
            [
                _summary(period='2026-02', tw=Decimal('0'), us=Decimal('0')),
                _summary(period='2026-03', tw=Decimal('0'), us=Decimal('0')),
            ],
            market='ALL',
        )
        fig = captured[0]
        assert _texts(fig, 0) == ['0', '0']
        assert _texts(fig, 1) == ['0', '0']

    def test_nan_period_skips_label_only_on_that_axes_e6(
        self, captured: list[Figure]
    ) -> None:
        # A runtime-None TW total drops that TW label; US labels are intact.
        second = _summary(period='2026-03')
        rows = [
            _summary(period='2026-02'),
            replace(second, pnl_tw_total=None),  # type: ignore[arg-type]
        ]
        chart_service.render_summary_chart(rows, market='ALL')
        fig = captured[0]
        assert _texts(fig, 0) == ['500,000']
        assert _texts(fig, 1) == ['8,000', '8,000']
