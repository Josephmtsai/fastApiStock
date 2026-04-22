"""Unit tests for fastapistock.repositories.portfolio_snapshot_repo."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapistock.repositories.portfolio_snapshot_repo import (
    PortfolioSnapshot,
    get_monthly,
    get_weekly,
    save_monthly,
    save_weekly,
)

_TZ = ZoneInfo('Asia/Taipei')


def _snap(
    pnl_tw: float = 523456.0,
    pnl_us: float = 8345.0,
    ts: datetime | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        pnl_tw=pnl_tw,
        pnl_us=pnl_us,
        timestamp=ts or datetime(2026, 4, 22, 21, 0, tzinfo=_TZ),
    )


def test_weekly_save_get_roundtrip() -> None:
    save_weekly(_snap(ts=datetime(2026, 4, 19, 21, 0, tzinfo=_TZ)))
    got = get_weekly('2026-04-19')
    assert got is not None
    assert got.pnl_tw == 523456.0
    assert got.pnl_us == 8345.0
    assert got.timestamp == datetime(2026, 4, 19, 21, 0, tzinfo=_TZ)


def test_monthly_save_get_roundtrip() -> None:
    save_monthly(_snap(ts=datetime(2026, 3, 31, 21, 0, tzinfo=_TZ)))
    got = get_monthly('2026-03')
    assert got is not None
    assert got.pnl_tw == 523456.0
    assert got.timestamp.year == 2026
    assert got.timestamp.month == 3


def test_get_weekly_missing_returns_none() -> None:
    assert get_weekly('2025-01-01') is None


def test_get_monthly_missing_returns_none() -> None:
    assert get_monthly('2020-01') is None


def test_overwrites_existing_snapshot() -> None:
    ts = datetime(2026, 4, 19, 21, 0, tzinfo=_TZ)
    save_weekly(_snap(pnl_tw=100.0, ts=ts))
    save_weekly(_snap(pnl_tw=999.0, ts=ts))
    got = get_weekly('2026-04-19')
    assert got is not None
    assert got.pnl_tw == 999.0
