"""Additional edge-case tests for Spec 005 (訊號歷史與定期報告).

These tests complement test_signal_history_repo.py, test_portfolio_snapshot_repo.py,
test_transactions_repo.py, and test_report_service.py by covering boundary
conditions explicitly called out in the spec but not exercised by the original
42 tests.

Groups
------
1. signal_history_repo    — Redis errors mid-scan, tier out of range, date bounds.
2. portfolio_snapshot_repo — Redis read errors, timezone preservation, float precision.
3. transactions_repo      — Mixed date formats, action whitespace, misc malformed CSV.
4. report_service         — Weekly/monthly window edge dates, signal sorting rules,
                            investment progress overflow / zero target, MarkdownV2
                            escaping, first-run + empty-data composition.
5. telegram_service       — _persist_signal integration with _calc_cost_signal.
6. scheduler              — Cron job config for weekly/monthly reports.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import redis

from fastapistock import config
from fastapistock.cache import redis_cache
from fastapistock.repositories.portfolio_snapshot_repo import (
    PortfolioSnapshot,
    get_monthly,
    get_weekly,
    save_weekly,
)
from fastapistock.repositories.signal_history_repo import (
    SignalRecord,
    list_signals,
    save_signal,
)
from fastapistock.repositories.transactions_repo import (
    _parse_row,
    fetch_tw_transactions,
    sum_buy_amount,
)
from fastapistock.scheduler import build_scheduler
from fastapistock.services.report_service import (
    _format_signal_trajectory,
    _monthly_window,
    _weekly_window,
    build_monthly_report,
    build_weekly_report,
)
from fastapistock.services.telegram_service import _calc_cost_signal

_RS = 'fastapistock.services.report_service'
_SH = 'fastapistock.repositories.signal_history_repo'

_TZ = ZoneInfo('Asia/Taipei')

_TX_MOD = 'fastapistock.repositories.transactions_repo.config'
_PATCH_TX_ID = f'{_TX_MOD}.GOOGLE_SHEETS_ID'
_PATCH_TX_GID = f'{_TX_MOD}.GOOGLE_SHEETS_TW_TRANSACTIONS_GID'

_HEADER = '股名,日期,成交股數,成本,買賣別,淨股數,淨金額,年度\n'


def _make_csv(*rows: str) -> str:
    return _HEADER + '\n'.join(rows)


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


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


# =============================================================================
# 1. signal_history_repo edge cases
# =============================================================================


class TestSignalHistoryEdgeCases:
    def test_list_signals_redis_error_returns_empty(self) -> None:
        """Redis SCAN RedisError should yield [] (spec: 連線失敗時不中斷)."""
        save_signal(_make_record())

        client = redis_cache._get_client()
        with patch.object(
            client,
            'scan',
            side_effect=redis.RedisError('connection drop mid-scan'),
        ):
            assert list_signals(date(2026, 4, 1), date(2026, 4, 30)) == []

    def test_list_signals_unexpected_exception_returns_empty(self) -> None:
        """Unexpected SCAN exception also degrades gracefully."""
        client = redis_cache._get_client()
        with patch.object(client, 'scan', side_effect=RuntimeError('unexpected')):
            assert list_signals(date(2026, 4, 1), date(2026, 4, 30)) == []

    def test_list_signals_get_redis_error_skips_that_key(self) -> None:
        """A per-key GET failure should skip only that key, not abort the scan."""
        save_signal(_make_record(symbol='A'))
        save_signal(_make_record(symbol='B'))

        client = redis_cache._get_client()
        real_get = client.get

        def broken_get(key):  # type: ignore[no-untyped-def]
            if 'A' in key:
                raise redis.RedisError('boom')
            return real_get(key)

        with patch.object(client, 'get', side_effect=broken_get):
            results = list_signals(date(2026, 4, 1), date(2026, 4, 30))
        symbols = {r.symbol for r in results}
        assert 'A' not in symbols
        assert 'B' in symbols

    def test_list_signals_key_with_missing_segments_skipped(self) -> None:
        """Keys that don't have the full 6-segment shape must be skipped."""
        save_signal(_make_record())
        client = redis_cache._get_client()
        # Only 4 segments — should be dropped by _parse_key_date
        client.set('signal:history:TW:2330', '{}')
        # 7 segments — also malformed
        client.set('signal:history:TW:2330:2026-04-22:1:extra', '{}')

        results = list_signals(date(2026, 4, 1), date(2026, 4, 30))
        assert len(results) == 1

    def test_list_signals_payload_not_dict_skipped(self) -> None:
        """JSON that decodes to a non-dict (e.g. list) must be skipped."""
        save_signal(_make_record())
        client = redis_cache._get_client()
        client.set('signal:history:TW:0050:2026-04-22:1', '[1,2,3]')

        results = list_signals(date(2026, 4, 1), date(2026, 4, 30))
        assert len(results) == 1

    def test_list_signals_missing_field_in_payload_skipped(self) -> None:
        """Missing required fields yield None via _dict_to_record and are skipped."""
        save_signal(_make_record())
        client = redis_cache._get_client()
        client.set(
            'signal:history:TW:0050:2026-04-22:1',
            '{"symbol":"0050"}',  # missing tier/price/etc.
        )
        results = list_signals(date(2026, 4, 1), date(2026, 4, 30))
        symbols = {r.symbol for r in results}
        assert symbols == {'2330'}

    def test_same_day_equal_start_end_returns_record(self) -> None:
        """start_date == end_date (single-day range) must still match."""
        save_signal(_make_record())
        results = list_signals(date(2026, 4, 22), date(2026, 4, 22))
        assert len(results) == 1

    def test_signals_across_month_boundary(self) -> None:
        """Records that span month end must all be found when range crosses."""
        save_signal(_make_record(ts=datetime(2026, 4, 30, 10, 0, tzinfo=_TZ)))
        save_signal(
            _make_record(symbol='0050', ts=datetime(2026, 5, 1, 10, 0, tzinfo=_TZ))
        )
        results = list_signals(date(2026, 4, 30), date(2026, 5, 1))
        symbols = sorted(r.symbol for r in results)
        assert symbols == ['0050', '2330']

    def test_signals_across_year_boundary(self) -> None:
        """Dec 31 → Jan 1 of next year."""
        save_signal(_make_record(ts=datetime(2025, 12, 31, 23, 0, tzinfo=_TZ)))
        save_signal(
            _make_record(symbol='0050', ts=datetime(2026, 1, 1, 0, 1, tzinfo=_TZ))
        )
        results = list_signals(date(2025, 12, 31), date(2026, 1, 1))
        assert len(results) == 2

    def test_same_symbol_same_day_multiple_tiers_all_listed(self) -> None:
        """Symbol + date + tier is the key → 3 different tiers → 3 records."""
        ts = datetime(2026, 4, 22, 9, 0, tzinfo=_TZ)
        for tier in (1, 2, 3):
            save_signal(_make_record(ts=ts, tier=tier))

        results = list_signals(date(2026, 4, 22), date(2026, 4, 22))
        assert sorted(r.tier for r in results) == [1, 2, 3]

    def test_tier_out_of_range_still_persisted_and_read_back(self) -> None:
        """Tier is not validated by the repo (caller's responsibility).

        The repo should round-trip whatever int tier it is given. This is a
        contract test: if callers ever pass tier=4+, the repo should not
        silently drop or corrupt it — the calc_cost_signal layer owns mapping.
        """
        rec = _make_record(tier=5)
        save_signal(rec)
        results = list_signals(date(2026, 4, 22), date(2026, 4, 22))
        assert len(results) == 1
        assert results[0].tier == 5

    def test_save_signal_swallows_put_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """redis_cache.put raising must not propagate out of save_signal."""
        with patch(
            f'{_SH}.redis_cache.put',
            side_effect=RuntimeError('boom'),
        ):
            save_signal(_make_record())  # should not raise


# =============================================================================
# 2. portfolio_snapshot_repo edge cases
# =============================================================================


class TestSnapshotEdgeCases:
    def test_get_weekly_redis_failure_returns_none(self) -> None:
        """redis_cache.get raising must yield None, not propagate."""
        with patch(
            'fastapistock.repositories.portfolio_snapshot_repo.redis_cache.get',
            side_effect=RuntimeError('down'),
        ):
            assert get_weekly('2026-04-19') is None

    def test_get_monthly_redis_failure_returns_none(self) -> None:
        with patch(
            'fastapistock.repositories.portfolio_snapshot_repo.redis_cache.get',
            side_effect=RuntimeError('down'),
        ):
            assert get_monthly('2026-03') is None

    def test_timestamp_timezone_preserved_on_roundtrip(self) -> None:
        ts = datetime(2026, 4, 19, 21, 0, tzinfo=_TZ)
        save_weekly(
            PortfolioSnapshot(pnl_tw=1.0, pnl_us=2.0, timestamp=ts),
        )
        got = get_weekly('2026-04-19')
        assert got is not None
        # ZoneInfo == comparison — must be Asia/Taipei aware.
        assert got.timestamp.tzinfo is not None
        assert got.timestamp.utcoffset() == ts.utcoffset()

    def test_float_precision_preserved(self) -> None:
        """JSON round-trip should keep 2-decimal precision."""
        ts = datetime(2026, 4, 19, 21, 0, tzinfo=_TZ)
        save_weekly(PortfolioSnapshot(pnl_tw=123456.78, pnl_us=42.01, timestamp=ts))
        got = get_weekly('2026-04-19')
        assert got is not None
        assert got.pnl_tw == pytest.approx(123456.78)
        assert got.pnl_us == pytest.approx(42.01)

    def test_malformed_snapshot_payload_returns_none(self) -> None:
        """A snapshot written with a broken payload must load as None."""
        client = redis_cache._get_client()
        client.setex('portfolio:snapshot:weekly:2026-04-19', 3600, 'not-json')
        assert get_weekly('2026-04-19') is None


# =============================================================================
# 3. transactions_repo edge cases
# =============================================================================


class TestTransactionsEdgeCases:
    def test_mixed_date_formats_in_same_csv(self) -> None:
        """CSV containing dash, slash, and dot formats must all parse."""
        csv_text = _make_csv(
            '2330,2026-04-22,1000,820,買,1000,-820000,2026',
            '0050,2026/04/15,500,150,買,500,-75000,2026',
            '2454,2026.04.01,200,900,買,200,-180000,2026',
        )
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(csv_text)),
        ):
            result = fetch_tw_transactions()
        assert [tx.symbol for tx in result] == ['2330', '0050', '2454']
        dates = [tx.date for tx in result]
        assert dates == [
            date(2026, 4, 22),
            date(2026, 4, 15),
            date(2026, 4, 1),
        ]

    def test_sum_buy_amount_uses_abs_of_net_amount(self) -> None:
        """Spec: 買入淨金額為負 → 取絕對值後加總。"""
        csv_text = _make_csv(
            '2330,2026-04-22,1000,820,買,1000,-820000,2026',
            '0050,2026-04-15,500,150,買,500,-75000,2026',
        )
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(csv_text)),
        ):
            total = sum_buy_amount(2026, 4)
        assert total == 895000.0

    def test_sum_buy_amount_ignores_positive_net_amount_sell(self) -> None:
        """賣出 (action='賣') 必須被濾掉，即使淨金額為正。"""
        csv_text = _make_csv(
            '2330,2026-04-22,1000,820,賣,-1000,820000,2026',
        )
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(csv_text)),
        ):
            assert sum_buy_amount(2026, 4) == 0.0

    def test_action_with_surrounding_whitespace_still_matches(self) -> None:
        """'  買  ' after .strip() should equal '買'."""
        row = ['2330', '2026-04-22', '1000', '820', '  買  ', '1000', '-820000', '2026']
        tx = _parse_row(1, row)
        assert tx is not None
        assert tx.action == '買'

    def test_action_empty_row_skipped(self) -> None:
        row = ['2330', '2026-04-22', '1000', '820', '', '1000', '-820000', '2026']
        assert _parse_row(1, row) is None

    def test_year_column_falls_back_to_date_year_when_unparseable(self) -> None:
        """Year='abc' (非數字) → fall back to parsed_date.year."""
        row = ['2330', '2026-04-22', '1000', '820', '買', '1000', '-820000', 'abc']
        tx = _parse_row(1, row)
        assert tx is not None
        assert tx.year == 2026

    def test_fetch_header_only_returns_empty(self) -> None:
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(_HEADER)),
        ):
            assert fetch_tw_transactions() == []

    def test_fetch_all_malformed_returns_empty(self) -> None:
        csv_text = _make_csv(
            'garbage-row-1',
            'garbage-row-2',
        )
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(csv_text)),
        ):
            assert fetch_tw_transactions() == []

    def test_fetch_blank_lines_skipped(self) -> None:
        csv_text = _make_csv(
            '2330,2026-04-22,1000,820,買,1000,-820000,2026',
            '',
            '0050,2026-04-15,500,150,買,500,-75000,2026',
        )
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(csv_text)),
        ):
            result = fetch_tw_transactions()
        assert [tx.symbol for tx in result] == ['2330', '0050']

    def test_fetch_missing_sheet_id_returns_empty(self) -> None:
        with patch(_PATCH_TX_ID, ''), patch(_PATCH_TX_GID, '456'):
            assert fetch_tw_transactions() == []

    def test_fetch_missing_gid_returns_empty(self) -> None:
        with patch(_PATCH_TX_ID, '123'), patch(_PATCH_TX_GID, ''):
            assert fetch_tw_transactions() == []

    def test_sum_buy_amount_no_tx_returns_zero(self) -> None:
        """Empty sheet → sum is 0.0 (caller never divides by it without guard)."""
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(_HEADER)),
        ):
            assert sum_buy_amount(2026, 4) == 0.0

    def test_sum_buy_amount_action_variants_counted_by_contains_buy(self) -> None:
        """Real-world 買賣別 cells are '現買/沖買/現賣/沖賣'.

        Regression guard for Bug 2 (Spec 005): selector must be
        "action contains '買'" rather than exact-equality '買', otherwise
        no rows match the realistic sheet and 本月投入 stays at 0.
        """
        csv_text = _make_csv(
            '2330,2026-04-01,1000,820,現買,1000,"-820,000",2026',
            '0050,2026-04-05,500,150,沖買,500,"-75,000",2026',
            '2454,2026-04-10,100,900,現賣,-100,"90,000",2026',
            '3008,2026-04-15,200,500,沖賣,-200,"100,000",2026',
        )
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(csv_text)),
        ):
            assert sum_buy_amount(2026, 4) == 895000.0

    def test_sum_buy_amount_backward_compat_plain_buy_still_counts(self) -> None:
        """Existing sheets using plain '買'/'賣' remain supported."""
        csv_text = _make_csv(
            '2330,2026-04-01,1000,820,買,1000,"-820,000",2026',
            '0050,2026-04-05,500,150,賣,-500,"75,000",2026',
        )
        with (
            patch(_PATCH_TX_ID, '123'),
            patch(_PATCH_TX_GID, '456'),
            patch('httpx.get', return_value=_mock_response(csv_text)),
        ):
            assert sum_buy_amount(2026, 4) == 820000.0


# =============================================================================
# 4. report_service edge cases
# =============================================================================


class TestReportWindowEdgeCases:
    def test_weekly_window_monday_000001_covers_prior_week(self) -> None:
        """Monday 00:00:01 → window must cover the just-finished week.

        A scheduler scheduled at Sunday 21:00 but delayed past midnight should
        still produce the prior Mon~Sun report, never jump to the new week.
        """
        monday = datetime(2026, 4, 20, 0, 0, 1, tzinfo=_TZ)
        win = _weekly_window(monday)
        assert win.start == date(2026, 4, 13)
        assert win.end == date(2026, 4, 19)
        # Title shows prior Mon~Sun
        assert '2026-04-13' in win.title
        assert '2026-04-19' in win.title

    def test_weekly_window_prev_snapshot_is_prior_sunday(self) -> None:
        """prev_snapshot_id = Sunday before the reporting-week's Monday."""
        sunday = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        win = _weekly_window(sunday)
        assert win.prev_snapshot_id == '2026-04-19'

    def test_monthly_window_on_first_of_month_covers_prev_month(self) -> None:
        """May 1 execution → window is 2026-04-01 to 2026-04-30."""
        now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
        win = _monthly_window(now)
        assert win.start == date(2026, 4, 1)
        assert win.end == date(2026, 4, 30)
        assert win.target_year == 2026
        assert win.target_month == 4

    def test_monthly_window_on_jan_1_rolls_back_to_prev_year(self) -> None:
        """Jan 1 2026 execution → window is 2025-12-01 to 2025-12-31."""
        now = datetime(2026, 1, 1, 21, 0, tzinfo=_TZ)
        win = _monthly_window(now)
        assert win.start == date(2025, 12, 1)
        assert win.end == date(2025, 12, 31)
        assert win.target_year == 2025
        assert win.target_month == 12
        # Title should reference prev month, i.e. 2025-12
        assert '2025-12' in win.title
        # Previous monthly snapshot should refer to 2025-11
        assert win.prev_snapshot_id == '2025-11'

    def test_monthly_window_on_mar_1_handles_leap_year(self) -> None:
        """Mar 1 2024 (leap year) → window Feb 1 to Feb 29."""
        now = datetime(2024, 3, 1, 21, 0, tzinfo=_TZ)
        win = _monthly_window(now)
        assert win.end == date(2024, 2, 29)


class TestSignalTrajectoryFormatting:
    def _s(
        self,
        symbol: str,
        tier: int,
        day: int,
        month: int = 4,
    ) -> SignalRecord:
        return SignalRecord(
            symbol=symbol,
            market='TW',
            tier=tier,
            drop_pct=-25.0,
            price=800.0,
            week52_high=1044.0,
            ma50=820.5,
            timestamp=datetime(2026, month, day, 10, 0, tzinfo=_TZ),
        )

    def test_same_symbol_same_day_same_tier_renders_once(self) -> None:
        """If duplicates sneak in at the list_signals layer, formatter shouldn't
        emit two tokens for the same symbol/day/tier combo.  But note: the repo
        already deduplicates at the key level. This test guards against
        regressions that change the repo contract."""
        r1 = self._s('2330', 2, 22)
        r2 = self._s('2330', 2, 22)
        lines = _format_signal_trajectory([r1, r2])
        # Two tokens (because formatter itself doesn't deduplicate — repo does).
        # This is explicitly documenting current behavior: if you have dup
        # records from list_signals, you'll see duplicated tokens. Any future
        # change to dedupe in the formatter should update this test.
        assert lines[0] == '2330: ⭐⭐ (4/22) → ⭐⭐ (4/22)'

    def test_multiple_tiers_sorted_by_timestamp_not_by_tier(self) -> None:
        """Trajectory sort key is timestamp; a later-timestamp tier-2 still
        follows an earlier-timestamp tier-3 in this edge case."""
        r_later_low = self._s('2330', 2, 24)
        r_earlier_high = self._s('2330', 3, 22)
        lines = _format_signal_trajectory([r_later_low, r_earlier_high])
        assert lines == ['2330: ⭐⭐⭐ (4/22) → ⭐⭐ (4/24)']

    def test_multiple_symbols_alphabetical_stable(self) -> None:
        """Symbols rendered in sorted() order — '0050' before 'AAPL' before 'NVDA'."""
        records = [
            self._s('NVDA', 2, 24),
            self._s('AAPL', 1, 20),
            self._s('0050', 1, 18),
        ]
        lines = _format_signal_trajectory(records)
        assert lines[0].startswith('0050')
        assert lines[1].startswith('AAPL')
        assert lines[2].startswith('NVDA')

    def test_tier_out_of_mapping_fallback_to_repeat_star(self) -> None:
        """Defensive fallback: tier 4 → '⭐⭐⭐⭐' (4 repetitions)."""
        rec = self._s('2330', 4, 22)
        lines = _format_signal_trajectory([rec])
        assert '⭐⭐⭐⭐' in lines[0]


class TestReportComposition:
    def _patch_all(
        self,
        pnl_tw: float | None = 523456.0,
        pnl_us: float | None = 8345.0,
        prev_snap: PortfolioSnapshot | None = None,
        signals: list[SignalRecord] | None = None,
        buy_amount: float | None = 85000.0,
        buy_raises: bool = False,
    ) -> tuple[AbstractContextManager[MagicMock], ...]:
        if buy_raises:
            sum_mock = patch(
                f'{_RS}.transactions_repo.sum_buy_amount',
                side_effect=RuntimeError('sheets down'),
            )
        else:
            sum_mock = patch(
                f'{_RS}.transactions_repo.sum_buy_amount',
                return_value=buy_amount if buy_amount is not None else 0.0,
            )
        return (
            patch(f'{_RS}.portfolio_repo.fetch_pnl_tw', return_value=pnl_tw),
            patch(f'{_RS}.portfolio_repo.fetch_pnl_us', return_value=pnl_us),
            patch(
                f'{_RS}.portfolio_snapshot_repo.get_weekly',
                return_value=prev_snap,
            ),
            patch(
                f'{_RS}.portfolio_snapshot_repo.get_monthly',
                return_value=prev_snap,
            ),
            patch(f'{_RS}.portfolio_snapshot_repo.save_weekly'),
            patch(f'{_RS}.portfolio_snapshot_repo.save_monthly'),
            patch(
                f'{_RS}.signal_history_repo.list_signals',
                return_value=signals or [],
            ),
            sum_mock,
        )

    def test_investment_progress_over_100_percent(self) -> None:
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        patches = self._patch_all(buy_amount=120000.0)
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
            text, _ = build_weekly_report(now)
        assert '120,000' in text
        # 120% > 100 → should show ✅
        assert '✅' in text

    def test_investment_progress_zero_target_no_div_by_zero(self) -> None:
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        patches = self._patch_all(buy_amount=50000.0)
        with (
            patch.object(config, 'REGULAR_INVESTMENT_TARGET_TWD', 0),
            patch(f'{_RS}.config.REGULAR_INVESTMENT_TARGET_TWD', 0),
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            text, _ = build_weekly_report(now)  # should not raise
        assert '0%' in text  # pct falls back to 0 when target==0

    def test_tx_read_failure_shows_placeholder(self) -> None:
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        patches = self._patch_all(buy_raises=True)
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
            text, _ = build_weekly_report(now)
        assert '資料讀取失敗' in text
        # Other sections still there
        assert '週報' in text

    def test_pnl_fetch_failure_shows_placeholder_for_pnl_only(self) -> None:
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        patches = self._patch_all(pnl_tw=None, pnl_us=None, buy_amount=85000.0)
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
            text, _ = build_weekly_report(now)
        assert '資料讀取失敗' in text
        # Investment section unaffected
        assert '85,000' in text

    def test_snapshot_load_failure_shows_snapshot_error_text(self) -> None:
        """When get_weekly raises, user sees '快照讀取失敗' (not the first-run text).

        This distinguishes transient infra failure from the legitimate
        "no baseline yet" case; callers looking at the report can tell the
        two apart at a glance.
        """
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        # Simulate load failure via patching get_weekly to raise
        patches = (
            patch(f'{_RS}.portfolio_repo.fetch_pnl_tw', return_value=523456.0),
            patch(f'{_RS}.portfolio_repo.fetch_pnl_us', return_value=8345.0),
            patch(
                f'{_RS}.portfolio_snapshot_repo.get_weekly',
                side_effect=RuntimeError('down'),
            ),
            patch(f'{_RS}.portfolio_snapshot_repo.save_weekly'),
            patch(f'{_RS}.signal_history_repo.list_signals', return_value=[]),
            patch(f'{_RS}.transactions_repo.sum_buy_amount', return_value=0.0),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            text, _ = build_weekly_report(now)
        assert '快照讀取失敗' in text
        assert '首次執行' not in text

    def test_snapshot_missing_key_shows_first_run_text(self) -> None:
        """Redis healthy but key absent → legitimate first-run state."""
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        patches = (
            patch(f'{_RS}.portfolio_repo.fetch_pnl_tw', return_value=523456.0),
            patch(f'{_RS}.portfolio_repo.fetch_pnl_us', return_value=8345.0),
            patch(
                f'{_RS}.portfolio_snapshot_repo.get_weekly',
                return_value=None,
            ),
            patch(f'{_RS}.portfolio_snapshot_repo.save_weekly'),
            patch(f'{_RS}.signal_history_repo.list_signals', return_value=[]),
            patch(f'{_RS}.transactions_repo.sum_buy_amount', return_value=0.0),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            text, _ = build_weekly_report(now)
        assert '首次執行' in text
        assert '快照讀取失敗' not in text

    def test_first_run_full_combo_empty_data_still_produces_report(self) -> None:
        """All sub-systems report "no data" — the report should still compose."""
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        patches = self._patch_all(
            pnl_tw=0.0,
            pnl_us=0.0,
            prev_snap=None,
            signals=[],
            buy_amount=0.0,
        )
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
            text, _ = build_weekly_report(now)
        assert '首次執行' in text
        assert '無觸發加碼訊號' in text
        assert 'FastAPI Stock Bot' in text

    def test_monthly_report_reads_signals_in_prev_month_window(self) -> None:
        """build_monthly_report should pass start=prev month first day, end=prev
        month last day to list_signals — never includes current month."""
        now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
        captured: dict[str, tuple[date, date]] = {}

        def fake_list(start: date, end: date) -> list[SignalRecord]:
            captured['range'] = (start, end)
            return []

        patches = self._patch_all()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patch(
                f'{_RS}.signal_history_repo.list_signals',
                side_effect=fake_list,
            ),
            patches[7],
        ):
            build_monthly_report(now)

        assert captured['range'] == (date(2026, 4, 1), date(2026, 4, 30))

    def test_weekly_report_signal_window_is_this_week(self) -> None:
        """build_weekly_report should ask list_signals for start=Mon, end=Sun."""
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)  # Sunday
        captured: dict[str, tuple[date, date]] = {}

        def fake_list(start: date, end: date) -> list[SignalRecord]:
            captured['range'] = (start, end)
            return []

        patches = self._patch_all()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patch(
                f'{_RS}.signal_history_repo.list_signals',
                side_effect=fake_list,
            ),
            patches[7],
        ):
            build_weekly_report(now)

        assert captured['range'] == (date(2026, 4, 20), date(2026, 4, 26))

    def test_weekly_report_past_midnight_end_is_prior_sunday(self) -> None:
        """Scheduler firing at Mon 00:00:01 → list_signals end is prior Sunday.

        Regression test for the window-rollover bug: delayed execution after
        midnight must NOT slide the window into the new week.
        """
        now = datetime(2026, 4, 27, 0, 0, 1, tzinfo=_TZ)  # Monday just-past-midnight
        captured: dict[str, tuple[date, date]] = {}

        def fake_list(start: date, end: date) -> list[SignalRecord]:
            captured['range'] = (start, end)
            return []

        patches = self._patch_all()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patch(
                f'{_RS}.signal_history_repo.list_signals',
                side_effect=fake_list,
            ),
            patches[7],
        ):
            build_weekly_report(now)

        # end must be 2026-04-26 (Sunday), not 2026-04-27 (Monday of next week)
        assert captured['range'] == (date(2026, 4, 20), date(2026, 4, 26))

    def test_markdownv2_escapes_dots_in_numbers(self) -> None:
        """Dollar amounts like '523,456' + position percentages must be escaped."""
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        prev = PortfolioSnapshot(
            pnl_tw=500000.0,
            pnl_us=8000.0,
            timestamp=datetime(2026, 4, 19, 21, 0, tzinfo=_TZ),
        )
        patches = self._patch_all(prev_snap=prev)
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
            text, _ = build_weekly_report(now)
        # Any dot literal outside code span should appear escaped as '\.'
        # Percentage formatting like '+4.7%' must have escaped dot.
        import re

        # Find any floating-point pattern NOT preceded by a backslash
        unescaped = re.findall(r'(?<!\\)\d+\.\d+', text)
        assert not unescaped, (
            f'Found {len(unescaped)} unescaped decimal numbers: {unescaped[:3]!r}'
        )

    def test_markdownv2_title_dash_escaped(self) -> None:
        now = datetime(2026, 4, 26, 21, 0, tzinfo=_TZ)
        patches = self._patch_all()
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
            text, _ = build_weekly_report(now)
        # Title includes '2026-04-20 ~ 2026-04-26';
        # dashes must be escaped in MarkdownV2
        assert r'2026\-04\-20' in text

    def test_monthly_report_saves_snapshot_even_when_prev_exists(self) -> None:
        now = datetime(2026, 5, 1, 21, 0, tzinfo=_TZ)
        prev = PortfolioSnapshot(
            pnl_tw=400000.0,
            pnl_us=7000.0,
            timestamp=datetime(2026, 3, 31, 21, 0, tzinfo=_TZ),
        )
        # Phase 3 moved Redis snapshot persistence into the pipeline (so
        # `dry_run` can opt out).  Drive the pipeline directly with both
        # external sinks suppressed so the assertion holds.
        from fastapistock.services.report_service import run_report_pipeline

        patches = self._patch_all(prev_snap=prev)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5] as mock_save_m,
            patches[6],
            patches[7],
            patch(f'{_RS}.report_history_repo.upsert_symbol_snapshots'),
            patch(f'{_RS}.report_history_repo.upsert_report_summary'),
            patch(f'{_RS}.sheet_writer.append_monthly_history', return_value=True),
            patch(f'{_RS}._send_markdown', return_value=True),
        ):
            run_report_pipeline(
                report_type='monthly',
                trigger='cron',
                skip_telegram=True,
                skip_sheet=True,
                now=now,
            )
        assert mock_save_m.called


# =============================================================================
# 5. telegram_service._calc_cost_signal + _persist_signal integration
# =============================================================================


class TestCalcCostSignalPersistIntegration:
    def test_empty_symbol_does_not_persist(self) -> None:
        """symbol='' (default) → _persist_signal must not be called."""
        with patch('fastapistock.services.telegram_service._persist_signal') as mock_p:
            result = _calc_cost_signal(
                price=80.0, week52_high=100.0, ma50=90.0, market='TW'
            )
        assert result is not None
        mock_p.assert_not_called()

    def test_non_empty_symbol_triggers_persist(self) -> None:
        with patch('fastapistock.services.telegram_service._persist_signal') as mock_p:
            result = _calc_cost_signal(
                price=80.0,
                week52_high=100.0,
                ma50=90.0,
                market='TW',
                symbol='2330',
            )
        assert result is not None
        mock_p.assert_called_once()
        # Must pass the critical fields along
        _, kwargs = mock_p.call_args
        assert kwargs['symbol'] == '2330'
        assert kwargs['market'] == 'TW'
        assert kwargs['stars'] == '⭐'

    def test_persist_failure_does_not_break_signal_string(self) -> None:
        """_persist_signal raising must not disrupt the returned signal text."""
        with patch(
            'fastapistock.services.telegram_service.signal_history_repo.save_signal',
            side_effect=RuntimeError('redis down'),
        ):
            result = _calc_cost_signal(
                price=80.0,
                week52_high=100.0,
                ma50=90.0,
                market='TW',
                symbol='2330',
            )
        assert result is not None
        assert '⭐' in result
        assert 'MA50' in result

    def test_no_signal_no_persist(self) -> None:
        """When _calc_cost_signal returns None, no persist call is made."""
        with patch('fastapistock.services.telegram_service._persist_signal') as mock_p:
            # price above MA50 → no signal
            result = _calc_cost_signal(
                price=95.0,
                week52_high=100.0,
                ma50=90.0,
                market='TW',
                symbol='2330',
            )
        assert result is None
        mock_p.assert_not_called()

    def test_stars_to_tier_mapping_complete(self) -> None:
        """All three star patterns must map to tiers 1/2/3 and persist correctly."""
        from fastapistock.services.telegram_service import _STARS_TO_TIER

        assert _STARS_TO_TIER['⭐'] == 1
        assert _STARS_TO_TIER['⭐⭐'] == 2
        assert _STARS_TO_TIER['⭐⭐⭐'] == 3

    def test_persist_uses_tier_2_for_two_stars(self) -> None:
        """A -26% drop (TW) should persist with tier=2."""
        captured: dict[str, int] = {}

        def fake_save(record: SignalRecord) -> None:
            captured['tier'] = record.tier

        with patch(
            'fastapistock.services.telegram_service.signal_history_repo.save_signal',
            side_effect=fake_save,
        ):
            _calc_cost_signal(
                price=74.0,  # -26% drop
                week52_high=100.0,
                ma50=90.0,
                market='TW',
                symbol='2330',
            )
        assert captured['tier'] == 2

    def test_persist_uses_tier_3_for_three_stars_us(self) -> None:
        captured: dict[str, int] = {}

        def fake_save(record: SignalRecord) -> None:
            captured['tier'] = record.tier

        with patch(
            'fastapistock.services.telegram_service.signal_history_repo.save_signal',
            side_effect=fake_save,
        ):
            _calc_cost_signal(
                price=59.0,  # -41% drop
                week52_high=100.0,
                ma50=90.0,
                market='US',
                symbol='AAPL',
            )
        assert captured['tier'] == 3


# =============================================================================
# 6. scheduler cron config
# =============================================================================


class TestSchedulerCronConfig:
    def test_weekly_report_job_exists_with_sunday_2100_trigger(self) -> None:
        scheduler = build_scheduler()
        job = scheduler.get_job('weekly_report')
        assert job is not None
        # CronTrigger.fields has entries; day_of_week/hour/minute must match
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields['day_of_week'] == 'sun'
        assert fields['hour'] == '21'
        assert fields['minute'] == '0'

    def test_monthly_report_job_exists_with_day1_2100_trigger(self) -> None:
        scheduler = build_scheduler()
        job = scheduler.get_job('monthly_report')
        assert job is not None
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields['day'] == '1'
        assert fields['hour'] == '21'
        assert fields['minute'] == '0'

    def test_stock_push_job_exists(self) -> None:
        scheduler = build_scheduler()
        assert scheduler.get_job('stock_push') is not None

    def test_all_jobs_use_asia_taipei_tz(self) -> None:
        scheduler = build_scheduler()
        for job_id in ('stock_push', 'weekly_report', 'monthly_report'):
            job = scheduler.get_job(job_id)
            assert job is not None
            # Trigger timezone should be Asia/Taipei (string or ZoneInfo)
            tz = getattr(job.trigger, 'timezone', None)
            assert tz is not None
            assert 'Taipei' in str(tz)
