"""QA supplemental tests for spec 020 (TW PnL #N/A fallback)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from fastapistock.services import portfolio_service
from tests.test_portfolio_repo_pnl import (
    _NUMERIC_I_SUM,
    _golden_rows,
    _price_returning,
    _run_tw,
)


def test_fallback_ignores_rows_at_and_after_summary_row() -> None:
    rows = _golden_rows()
    # Row 18 (summary) and anything after it must never be scanned as holdings.
    rows[18] = ['9999', 'X', '100', '1', '0', '', '', '', '#N/A', '']
    rows.append(['8888', 'Y', '100', '1', '0', '', '', '', '7000000', ''])

    result, _ = _run_tw(rows, _price_returning(60.0))

    assert result == pytest.approx(5792545.0)


def test_fallback_symbol_with_whitespace_is_stripped_for_price_lookup() -> None:
    rows = _golden_rows()
    rows[1][0] = ' 0050 '
    price = _price_returning(60.0)

    result, _ = _run_tw(rows, price)

    assert result == pytest.approx(5792545.0)
    price.assert_called_once_with('0050')


def test_fallback_whitespace_only_symbol_row_is_skipped() -> None:
    rows = _golden_rows()
    rows[4] = ['   ', 'X', '100', '1', '0', '', '', '', '999999', '']

    result, _ = _run_tw(rows, _price_returning(60.0))

    assert result == pytest.approx(5792545.0)


def test_fallback_accepts_thousand_separators_in_shares_and_totals() -> None:
    rows = _golden_rows()
    rows[1][2] = '149,957'
    rows[1][3] = '8,339,244'
    rows[1][4] = '0'

    result, _ = _run_tw(rows, _price_returning(60.0))

    assert result == pytest.approx(5792545.0)


def test_fallback_negative_shares_row_is_ignored() -> None:
    rows = _golden_rows()
    rows[4] = ['9901', 'X', '-100', '1', '0', '', '', '', '999999', '']
    price = _price_returning(60.0)

    result, _ = _run_tw(rows, price)

    assert result == pytest.approx(5792545.0)
    price.assert_called_once_with('0050')


def test_fallback_multiple_na_holdings_all_recomputed() -> None:
    rows = _golden_rows()
    rows[3][8] = '#N/A'  # 2330 shares 3345, D 4646352, E 373462

    def _lookup(code: str) -> MagicMock:
        return MagicMock(price={'0050': 60.0, '2330': 2550.0}[code])

    price = MagicMock(side_effect=_lookup)

    result, _ = _run_tw(rows, price)

    expected = (
        _NUMERIC_I_SUM
        - 4156860
        + (149957 * 60.0 - 8339244)
        + (3345 * 2550.0 - (4646352 - 373462))
    )
    assert result == pytest.approx(expected)
    assert price.call_count == 2


def test_fallback_price_lookup_returning_object_without_price_returns_none() -> None:
    price = MagicMock(return_value=object())

    result, mock_cache = _run_tw(_golden_rows(), price)

    assert result is None
    mock_cache.put.assert_not_called()


def test_fallback_negative_total_pnl_is_returned() -> None:
    rows = _golden_rows()
    for row in (rows[3], rows[7], rows[11], rows[14], rows[15], rows[16]):
        row[8] = '-1000'

    result, _ = _run_tw(rows, _price_returning(1.0))

    assert result == pytest.approx(-6000 + (149957 * 1.0 - 8339244))


def test_fallback_not_cached_across_calls_refetches_each_time() -> None:
    price = _price_returning(60.0)
    first, cache = _run_tw(_golden_rows(), price)
    second, _ = _run_tw(_golden_rows(), price)

    assert first == second
    assert price.call_count == 2
    cache.put.assert_not_called()


def _service_patches(rows: list[list[str]], price: MagicMock):  # type: ignore[no-untyped-def]
    import csv
    import io

    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    response = MagicMock()
    response.text = buf.getvalue()
    cfg = MagicMock()
    cfg.GOOGLE_SHEETS_ID = 'sid'
    cfg.GOOGLE_SHEETS_PORTFOLIO_GID_TW = 'gid'
    cfg.PORTFOLIO_CACHE_TTL = 60
    cache = MagicMock()
    cache.get.return_value = None
    return (
        patch('fastapistock.repositories.portfolio_repo.redis_cache', cache),
        patch('fastapistock.repositories.portfolio_repo.config', cfg),
        patch(
            'fastapistock.repositories.portfolio_repo.httpx.get',
            return_value=response,
        ),
        patch('fastapistock.services.stock_service.get_rich_tw_stock', price),
    )


def test_save_daily_close_snapshot_tw_saves_fallback_value() -> None:
    p1, p2, p3, p4 = _service_patches(_golden_rows(), _price_returning(60.0))
    with (
        p1,
        p2,
        p3,
        p4,
        patch.object(portfolio_service, 'portfolio_snapshot_repo') as repo,
    ):
        ok = portfolio_service.save_daily_close_snapshot(
            market='TW',
            trading_date='2026-10-12',
            captured_at=datetime(2026, 10, 12, 14, 0),
        )

    assert ok is True
    saved = repo.save_daily.call_args.args[2]
    assert saved.pnl_tw == pytest.approx(5792545.0)


def test_save_daily_close_snapshot_tw_returns_false_when_fallback_fails() -> None:
    price = MagicMock(side_effect=RuntimeError('down'))
    p1, p2, p3, p4 = _service_patches(_golden_rows(), price)
    with (
        p1,
        p2,
        p3,
        p4,
        patch.object(portfolio_service, 'portfolio_snapshot_repo') as repo,
    ):
        ok = portfolio_service.save_daily_close_snapshot(
            market='TW',
            trading_date='2026-10-12',
            captured_at=datetime(2026, 10, 12, 14, 0),
        )

    assert ok is False
    repo.save_daily.assert_not_called()


def test_get_daily_pnl_delta_reply_tw_uses_fallback_value() -> None:
    p1, p2, p3, p4 = _service_patches(_golden_rows(), _price_returning(60.0))
    snapshot = MagicMock(pnl_tw=5000000.0)
    with (
        p1,
        p2,
        p3,
        p4,
        patch.object(portfolio_service, 'portfolio_snapshot_repo') as repo,
    ):
        repo.get_daily.return_value = snapshot
        text = portfolio_service.get_daily_pnl_delta_reply(
            market='TW', trading_date='2026-10-12'
        )

    assert '5,792,545' in text
    assert '792,545' in text
