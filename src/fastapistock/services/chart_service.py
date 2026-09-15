"""PNG chart rendering for the ``/history`` flow (spec-018, spec-019).

Uses matplotlib's object-oriented API only (``Figure`` + ``FigureCanvasAgg``)
so rendering is GUI-free, thread-safe and holds no global state. Importing
``matplotlib.pyplot`` is deliberately avoided: it would require a
``matplotlib.use('Agg')`` call before the import, which trips Ruff E402.

All chart labels are ASCII so the default DejaVu font bundled with the
matplotlib wheel renders them without extra font installation.

spec-019 adds axis titles (period / currency), thousands-separated ticks,
per-point value labels, an in-axes pnl% text box and renders the ``'ALL'``
summary as two stacked sharex subplots instead of a twinx dual axis.
"""

from __future__ import annotations

import io
import math
from decimal import Decimal

from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import StrMethodFormatter

from fastapistock.repositories.report_history_repo import (
    ReportSummary,
    SymbolSnapshot,
)

_FIGSIZE = (8.0, 4.5)
_FIGSIZE_STACKED = (8.0, 6.5)
_DPI = 100
_PRICE_DECIMALS = 2  # matches history_handler._format_decimal ('{:,.2f}')
_PNL_DECIMALS = 0  # P&L amounts: integer thousands for ticks and labels
_LABEL_FONTSIZE = 8
_CURRENCY_BY_MARKET = {'TW': 'TWD', 'US': 'USD'}


def render_symbol_chart(rows: list[SymbolSnapshot]) -> bytes:
    """Render close-price (solid) vs avg-cost (dashed) chart as PNG bytes.

    Every non-NaN close point is labelled with its value, the last avg-cost
    point is labelled too, and the last ``pnl_pct`` (when available) is shown
    in a text box anchored to the top-right corner of the axes.

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
    _plot_symbol_lines(ax, periods, close, avg_cost)
    _annotate_pnl_box(ax, ordered[-1].pnl_pct)
    first = ordered[0]
    ax.set_title(f'{first.symbol} ({first.market}) {first.report_type}')
    ax.set_ylabel(_price_ylabel(first.market))
    ax.legend()
    # Extra headroom: the top-right pnl box must not cover the last label.
    ax.margins(x=0.08, y=0.25)
    _style_y_axis(ax, decimals=_PRICE_DECIMALS)
    _style_x_axis(ax, first.report_type)
    return _fig_to_png(fig)


def render_summary_chart(
    summaries: list[ReportSummary],
    *,
    market: str = 'ALL',
) -> bytes:
    """Render TW/US unrealized-PnL trend chart as PNG bytes.

    ``market='ALL'`` draws two stacked subplots sharing the X axis: TW (TWD)
    on top and US (USD) below, each with its own Y scale. ``'TW'`` / ``'US'``
    draws a single line on a single axis labelled with the matching currency.

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
    report_type = ordered[0].report_type

    if market == 'ALL':
        fig = Figure(figsize=_FIGSIZE_STACKED, dpi=_DPI)
        _render_stacked_summary(fig, periods, tw, us, report_type)
        return _fig_to_png(fig)

    fig = Figure(figsize=_FIGSIZE, dpi=_DPI)
    ax = fig.add_subplot(111)
    ax.set_title(f'Account P&L ({report_type})')
    values, label = (tw, 'TW P&L (TWD)') if market == 'TW' else (us, 'US P&L (USD)')
    _plot_pnl_series(ax, periods, values, label=label)
    _style_x_axis(ax, report_type)
    return _fig_to_png(fig)


def _plot_symbol_lines(
    ax: Axes,
    periods: list[str],
    close: list[float],
    avg_cost: list[float],
) -> None:
    """Draw close (solid) and avg-cost (dashed) lines plus their value labels."""
    has_avg_cost = not all(math.isnan(v) for v in avg_cost)
    ax.plot(periods, close, marker='o', linestyle='-', label='close')
    if has_avg_cost:
        ax.plot(periods, avg_cost, marker='o', linestyle='--', label='avg cost')
    _label_points(ax, periods, close, decimals=_PRICE_DECIMALS)
    if has_avg_cost:
        _label_points(ax, periods, avg_cost, decimals=_PRICE_DECIMALS, only_last=True)


def _render_stacked_summary(
    fig: Figure,
    periods: list[str],
    tw: list[float],
    us: list[float],
    report_type: str,
) -> None:
    """Lay out the ``'ALL'`` summary as TW (top) / US (bottom) sharex subplots."""
    ax_tw = fig.add_subplot(211)
    ax_us = fig.add_subplot(212, sharex=ax_tw)
    ax_tw.set_title(f'Account P&L ({report_type})')
    _plot_pnl_series(ax_tw, periods, tw, label='TW P&L (TWD)')
    _plot_pnl_series(ax_us, periods, us, label='US P&L (USD)')
    # Shared X: hide the top tick labels, put the axis title only at the bottom.
    ax_tw.tick_params(axis='x', labelbottom=False)
    _style_x_axis(ax_us, report_type)


def _plot_pnl_series(
    ax: Axes,
    periods: list[str],
    values: list[float],
    *,
    label: str,
) -> None:
    """Draw one P&L line with ylabel, legend, value labels and Y styling."""
    ax.plot(periods, values, marker='o', linestyle='-', label=label)
    ax.set_ylabel(label)
    ax.legend()
    _label_points(ax, periods, values, decimals=_PNL_DECIMALS)
    ax.margins(x=0.08, y=0.15)
    _style_y_axis(ax, decimals=_PNL_DECIMALS)


def _label_points(
    ax: Axes,
    periods: list[str],
    values: list[float],
    *,
    decimals: int,
    only_last: bool = False,
) -> None:
    """Annotate each non-NaN point (or only the last one) with its value.

    Args:
        ax: Target axes.
        periods: X categories, aligned with ``values``.
        values: Y values; NaN entries produce no label.
        decimals: Number of decimals in the ``{:,.Nf}`` label.
        only_last: Label index ``-1`` only; skipped when that value is NaN.
    """
    indices = [len(values) - 1] if only_last else range(len(values))
    for i in indices:
        value = values[i]
        if math.isnan(value):
            continue
        ax.annotate(
            f'{value:,.{decimals}f}',
            xy=(periods[i], value),
            xytext=(0, 6),
            textcoords='offset points',
            ha='center',
            va='bottom',
            fontsize=_LABEL_FONTSIZE,
        )


def _annotate_pnl_box(ax: Axes, pnl_pct: Decimal | None) -> None:
    """Show the signed pnl% in a boxed text at the axes' top-right corner.

    Anchored in axes-fraction coordinates so it never falls outside the plot
    regardless of the data range. No-op when ``pnl_pct`` is ``None``.
    """
    if pnl_pct is None:
        return
    ax.text(
        0.98,
        0.95,
        f'PnL {float(pnl_pct):+.2f}%',
        transform=ax.transAxes,
        ha='right',
        va='top',
        fontsize=9,
        bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.8},
    )


def _price_ylabel(market: str) -> str:
    """Return ``'Price (TWD)'`` / ``'Price (USD)'``; plain ``'Price'`` otherwise."""
    currency = _CURRENCY_BY_MARKET.get(market)
    return f'Price ({currency})' if currency else 'Price'


def _thousands_formatter(decimals: int) -> StrMethodFormatter:
    """Build a ``{x:,.Nf}`` tick formatter (thousands separator)."""
    return StrMethodFormatter(f'{{x:,.{decimals}f}}')


def _style_y_axis(ax: Axes, *, decimals: int) -> None:
    """Apply the thousands formatter and a faint horizontal-only grid."""
    ax.yaxis.set_major_formatter(_thousands_formatter(decimals))
    ax.grid(True, axis='y', linestyle=':', alpha=0.4)


def _to_float_series(values: list[Decimal | None]) -> list[float]:
    """Convert Decimals to floats, mapping ``None`` to NaN (line gap)."""
    return [float(v) if v is not None else math.nan for v in values]


def _style_x_axis(ax: Axes, report_type: str) -> None:
    """Title the X axis with the report period and rotate the tick labels."""
    ax.set_xlabel(f'Report period ({report_type})')
    ax.tick_params(axis='x', labelrotation=45)


def _fig_to_png(fig: Figure) -> bytes:
    """Rasterize a Figure through the Agg canvas and return PNG bytes."""
    fig.tight_layout()
    canvas = FigureCanvasAgg(fig)
    buf = io.BytesIO()
    # matplotlib ships partial stubs; print_png is untyped upstream.
    canvas.print_png(buf)  # type: ignore[no-untyped-call]
    return buf.getvalue()
