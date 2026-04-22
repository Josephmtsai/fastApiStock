"""Unit tests for fastapistock.repositories.signal_history_repo."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapistock.cache import redis_cache
from fastapistock.repositories.signal_history_repo import (
    SignalRecord,
    list_signals,
    save_signal,
)

_TZ = ZoneInfo('Asia/Taipei')


def _make_record(
    symbol: str = '2330',
    market: str = 'TW',
    tier: int = 2,
    ts: datetime | None = None,
    drop_pct: float = -26.5,
    price: float = 800.0,
) -> SignalRecord:
    return SignalRecord(
        symbol=symbol,
        market=market,
        tier=tier,
        drop_pct=drop_pct,
        price=price,
        week52_high=1044.0,
        ma50=820.5,
        timestamp=ts or datetime(2026, 4, 22, 10, 30, tzinfo=_TZ),
    )


def test_save_then_list_roundtrip_single_record() -> None:
    record = _make_record()
    save_signal(record)

    results = list_signals(date(2026, 4, 22), date(2026, 4, 22))
    assert len(results) == 1
    r = results[0]
    assert r.symbol == '2330'
    assert r.market == 'TW'
    assert r.tier == 2
    assert r.drop_pct == -26.5
    assert r.price == 800.0
    assert r.week52_high == 1044.0
    assert r.ma50 == 820.5
    assert r.timestamp == datetime(2026, 4, 22, 10, 30, tzinfo=_TZ)


def test_list_signals_filters_by_date_range() -> None:
    old = _make_record(ts=datetime(2026, 4, 10, 10, 0, tzinfo=_TZ))
    inside = _make_record(
        symbol='0050',
        ts=datetime(2026, 4, 15, 10, 0, tzinfo=_TZ),
        tier=1,
    )
    future = _make_record(
        symbol='2454',
        ts=datetime(2026, 5, 1, 10, 0, tzinfo=_TZ),
        tier=3,
    )
    for rec in (old, inside, future):
        save_signal(rec)

    results = list_signals(date(2026, 4, 13), date(2026, 4, 19))
    assert [r.symbol for r in results] == ['0050']


def test_save_same_day_same_tier_dedupes() -> None:
    ts1 = datetime(2026, 4, 22, 9, 0, tzinfo=_TZ)
    ts2 = datetime(2026, 4, 22, 14, 0, tzinfo=_TZ)
    save_signal(_make_record(ts=ts1, drop_pct=-25.0))
    save_signal(_make_record(ts=ts2, drop_pct=-27.5))

    results = list_signals(date(2026, 4, 22), date(2026, 4, 22))
    # Same key => only one row; the later write overwrites.
    assert len(results) == 1
    assert results[0].drop_pct == -27.5


def test_save_different_tiers_same_day_keeps_both() -> None:
    ts = datetime(2026, 4, 22, 9, 0, tzinfo=_TZ)
    save_signal(_make_record(ts=ts, tier=2))
    save_signal(_make_record(ts=ts, tier=3))

    results = list_signals(date(2026, 4, 22), date(2026, 4, 22))
    tiers = sorted(r.tier for r in results)
    assert tiers == [2, 3]


def test_list_signals_returns_empty_for_reversed_range() -> None:
    save_signal(_make_record())
    assert list_signals(date(2026, 4, 30), date(2026, 4, 1)) == []


def test_list_signals_skips_non_signal_keys() -> None:
    """Other Redis keys (e.g. from other caches) must be ignored by SCAN filter."""
    save_signal(_make_record())
    # write a random unrelated key
    client = redis_cache._get_client()
    client.set('some:other:key', 'xxx')

    results = list_signals(date(2026, 4, 1), date(2026, 4, 30))
    assert len(results) == 1


def test_list_signals_skips_malformed_value() -> None:
    save_signal(_make_record())
    client = redis_cache._get_client()
    client.set('signal:history:TW:9999:2026-04-22:1', 'not-json')

    results = list_signals(date(2026, 4, 1), date(2026, 4, 30))
    assert len(results) == 1
    assert results[0].symbol == '2330'


def test_list_signals_skips_malformed_key_date() -> None:
    save_signal(_make_record())
    client = redis_cache._get_client()
    client.set('signal:history:TW:9999:not-a-date:1', '{}')

    results = list_signals(date(2026, 4, 1), date(2026, 4, 30))
    assert len(results) == 1


def test_save_then_list_across_tz_preserves_date() -> None:
    ts = datetime(2026, 4, 22, 23, 59, tzinfo=_TZ)
    save_signal(_make_record(ts=ts))
    # Adding timedelta to confirm key date equals ts.date() (Asia/Taipei local)
    assert list_signals(ts.date(), ts.date() + timedelta(days=0))
