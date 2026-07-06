"""PNG chart rendering for the ``/history`` flow (spec-018).

Uses matplotlib's object-oriented API only (``Figure`` + ``FigureCanvasAgg``)
so rendering is GUI-free, thread-safe and holds no global state. Importing
``matplotlib.pyplot`` is deliberately avoided: it would require a
``matplotlib.use('Agg')`` call before the import, which trips Ruff E402.

All chart labels are ASCII so the default DejaVu font bundled with the
matplotlib wheel renders them without extra font installation.
"""

from __future__ import annotations

import io
import math
from decimal import Decimal

from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
)

_FIGSIZE = (8.0, 4.5)
_DPI = 100


def render_symbol_chart(rows: list[SymbolSnapshot]) -> bytes:
    """Render close-price (solid) vs avg-cost (dashed) chart as PNG bytes.

    The last data point is annotated with its ``pnl_pct`` when available.

    Args:
        rows: Per-symbol snapshot rows; any order, re-sorted by period.

    Returns:
        PNG image bytes.

    Raises:
        ValueError: When ``rows`` is empty.
    """
    if not rows:
        raise ValueError('rows must not be empty')
    ordered = sorted(rows, key=lambda r: r.report_period)
    periods = [r.report_period for r in ordered]
    close = _to_float_series([r.current_price for r in ordered])
    avg_cost = _to_float_series([r.avg_cost for r in ordered])

    fig = Figure(figsize=_FIGSIZE, dpi=_DPI)
    ax = fig.add_subplot(111)
    ax.plot(periods, close, marker='o', linestyle='-', label='close')
    if not all(math.isnan(v) for v in avg_cost):
        ax.plot(periods, avg_cost, marker='o', linestyle='--', label='avg cost')
    _annotate_last_pnl(ax, periods, close, ordered[-1].pnl_pct)
    first = ordered[0]
    ax.set_title(f'{first.symbol} ({first.market}) {first.report_type}')
    ax.set_ylabel('Price')
    ax.legend()
    _style_x_axis(ax)
    return _fig_to_png(fig)


def render_summary_chart(
    summaries: list[ReportSummary],
    *,
    market: str = 'ALL',
) -> bytes:
    """Render TW/US unrealized-PnL trend chart as PNG bytes.

    ``market='ALL'`` draws a dual y-axis chart: TW line on the left axis
    (TWD) and US line on the right axis (USD). ``'TW'`` / ``'US'`` draws a
    single line on a single axis labelled with the matching currency.

    Args:
        summaries: Aggregated summary rows; any order, re-sorted by period.
        market: ``'TW'``, ``'US'`` or ``'ALL'``.

    Returns:
        PNG image bytes.

    Raises:
        ValueError: When ``summaries`` is empty or ``market`` is unknown.
    """
    if not summaries:
        raise ValueError('summaries must not be empty')
    if market not in {'TW', 'US', 'ALL'}:
        raise ValueError(f'unknown market: {market!r}')
    ordered = sorted(summaries, key=lambda s: s.report_period)
    periods = [s.report_period for s in ordered]
    tw = _to_float_series([s.pnl_tw_total for s in ordered])
    us = _to_float_series([s.pnl_us_total for s in ordered])

    fig = Figure(figsize=_FIGSIZE, dpi=_DPI)
    ax = fig.add_subplot(111)
    ax.set_title(f'Account P&L ({ordered[0].report_type})')
    if market == 'ALL':
        _plot_dual_axis(ax, periods, tw, us)
    else:
        values, label = (tw, 'TW P&L (TWD)') if market == 'TW' else (us, 'US P&L (USD)')
        ax.plot(periods, values, marker='o', linestyle='-', label=label)
        ax.set_ylabel(label)
        ax.legend()
    _style_x_axis(ax)
    return _fig_to_png(fig)


def _plot_dual_axis(
    ax: Axes,
    periods: list[str],
    tw: list[float],
    us: list[float],
) -> None:
    """Draw the TW (left axis) and US (right axis) PnL lines with one legend."""
    ax_right = ax.twinx()
    (tw_line,) = ax.plot(
        periods, tw, marker='o', linestyle='-', color='C0', label='TW P&L (TWD)'
    )
    (us_line,) = ax_right.plot(
        periods, us, marker='o', linestyle='-', color='C1', label='US P&L (USD)'
    )
    ax.set_ylabel('TW P&L (TWD)')
    ax_right.set_ylabel('US P&L (USD)')
    ax.legend(handles=[tw_line, us_line])


def _annotate_last_pnl(
    ax: Axes,
    periods: list[str],
    close: list[float],
    pnl_pct: Decimal | None,
) -> None:
    """Annotate the last close point with its signed pnl%, if defined."""
    if pnl_pct is None or math.isnan(close[-1]):
        return
    ax.annotate(
        f'{float(pnl_pct):+.2f}%',
        xy=(periods[-1], close[-1]),
        xytext=(5, 5),
        textcoords='offset points',
    )


def _to_float_series(values: list[Decimal | None]) -> list[float]:
    """Convert Decimals to floats, mapping ``None`` to NaN (line gap)."""
    return [float(v) if v is not None else math.nan for v in values]


def _style_x_axis(ax: Axes) -> None:
    """Rotate period tick labels so YYYY-MM-DD strings do not overlap."""
    ax.tick_params(axis='x', labelrotation=45)


def _fig_to_png(fig: Figure) -> bytes:
    """Rasterize a Figure through the Agg canvas and return PNG bytes."""
    fig.tight_layout()
    canvas = FigureCanvasAgg(fig)
    buf = io.BytesIO()
    # matplotlib ships partial stubs; print_png is untyped upstream.
    canvas.print_png(buf)  # type: ignore[no-untyped-call]
    return buf.getvalue()
