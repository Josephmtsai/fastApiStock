"""Unit tests for fastapistock.services.report_service (happy-path builders)."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from fastapistock.repositories.portfolio_snapshot_repo import PortfolioSnapshot
from fastapistock.repositories.signal_history_repo import SignalRecord
from fastapistock.services.report_service import (
    _format_signal_trajectory,
    build_monthly_report,
    build_weekly_report,
)

_RS = 'fastapistock.services.report_service'

_TZ = ZoneInfo('Asia/Taipei')


def _signal(
    symbol: str,
    tier: int,
    day: int,
    market: str = 'TW',
    month: int = 4,
) -> SignalRecord:
    return SignalRecord(
        symbol=symbol,
        market=market,
        tier=tier,
        drop_pct=-25.0,
        price=800.0,
        week52_high=1044.0,
        ma50=820.5,
        timestamp=datetime(2026, month, day, 10, 0, tzinfo=_TZ),
    )


# ── _format_signal_trajectory ─────────────────────────────────────────────


def test_trajectory_single_entry() -> None:
    lines = _format_signal_trajectory([_signal('0050', 1, 18)])
    assert lines == ['0050: ⭐ (4/18)']


def test_trajectory_multi_tier_sorted_by_timestamp() -> None:
    records = [
        _signal('2330', 3, 24),
        _signal('2330', 2, 22),
    ]
    lines = _format_signal_trajectory(records)
    assert lines == ['2330: ⭐⭐ (4/22) → ⭐⭐⭐ (4/24)']


def test_trajectory_multiple_symbols_sorted_alphabetically() -> None:
    records = [
        _signal('AAPL', 1, 20, market='US'),
        _signal('0050', 1, 18),
    ]
    lines = _format_signal_trajectory(records)
    assert lines == ['0050: ⭐ (4/18)', 'AAPL: ⭐ (4/20)']


# ── build_weekly_report ───────────────────────────────────────────────────


def _patch_repos(
    pnl_tw: float | None = 523456.0,
    pnl_us: float | None = 8345.0,
    prev_tw: float | None = 500000.0,
    prev_us: float | None = 8000.0,
    signals: list[SignalRecord] | None = None,
    buy_amount: float = 85000.0,
) -> tuple[AbstractContextManager[MagicMock], ...]:
    prev = None
    if prev_tw is not None and prev_us is not None:
        prev = PortfolioSnapshot(
            pnl_tw=prev_tw,
            pnl_us=prev_us,
            timestamp=datetime(2026, 4, 12, 21, 0, tzinfo=_TZ),
        )
    return (
        patch(f'{_RS}.portfolio_repo.fetch_pnl_tw', return_value=pnl_tw),
        patch(f'{_RS}.portfolio_repo.fetch_pnl_us', return_value=pnl_us),
        patch(f'{_RS}.portfolio_snapshot_repo.get_weekly', return_value=prev),
        patch(f'{_RS}.portfolio_snapshot_repo.get_monthly', return_value=prev),
        patch(f'{_RS}.portfolio_snapshot_repo.save_weekly'),
        patch(f'{_RS}.portfolio_snapshot_repo.save_monthly'),
        patch(
            f'{_RS}.signal_history_repo.list_signals',
            return_value=signals or [],
        ),
        patch(
            f'{_RS}.transactions_repo.sum_buy_amount',
            return_value=buy_amount,
        ),
    )


def test_build_weekly_report_happy_path() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)  # Sunday
    signals = [_signal('2330', 2, 22), _signal('2330', 3, 24), _signal('0050', 1, 20)]
    patches = _patch_repos(signals=signals)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        text = build_weekly_report(now)

    # title
    assert '週報' in text
    # current PnL
    assert '523,456' in text
    assert '8,345' in text
    # signal trajectory content
    assert '2330' in text
    assert '0050' in text
    # count summary
    assert '共觸發 2 檔' in text
    # investment section
    assert '85,000' in text
    assert '100,000' in text


def test_build_weekly_report_first_run_no_prev_snapshot() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    patches = _patch_repos(prev_tw=None, prev_us=None)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        text = build_weekly_report(now)

    assert '首次執行' in text


def test_build_weekly_report_empty_signals() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    patches = _patch_repos(signals=[])
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        text = build_weekly_report(now)

    assert '無觸發加碼訊號' in text


def test_build_monthly_report_happy_path() -> None:
    now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
    signals = [
        _signal('2330', 2, 15),
        _signal('2330', 3, 22),
        _signal('0050', 1, 18),
        _signal('AAPL', 1, 20, market='US'),
        _signal('NVDA', 2, 24, market='US'),
    ]
    patches = _patch_repos(signals=signals)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        text = build_monthly_report(now)

    assert '月報' in text
    # '2026-04' appears in the title but '-' is MarkdownV2-escaped
    assert '2026' in text
    assert '共觸發 4 檔' in text
    assert '本月定額達成' in text


def test_build_monthly_report_saves_snapshot_for_prev_month() -> None:
    now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
    patches = _patch_repos()
    save_monthly_patch = patches[5]
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        save_monthly_patch as mock_save,
        patches[6],
        patches[7],
    ):
        build_monthly_report(now)
        assert mock_save.called
        args, _kwargs = mock_save.call_args
        snap = args[0]
        # Snapshot should be anchored to the last day of prev month (2026-04-30)
        assert snap.timestamp.year == 2026
        assert snap.timestamp.month == 4


def test_build_weekly_report_fetch_failure_shows_placeholder() -> None:
    now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
    patches = _patch_repos(pnl_tw=None, pnl_us=None, prev_tw=None, prev_us=None)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        text = build_weekly_report(now)

    assert '資料讀取失敗' in text
