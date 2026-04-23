"""Unit tests for fastapistock.repositories.transactions_repo."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import httpx

from fastapistock.repositories.transactions_repo import (
    _parse_date,
    _parse_number,
    _parse_row,
    fetch_tw_transactions,
    sum_buy_amount,
)

_MOD = 'fastapistock.repositories.transactions_repo.config'
_PATCH_ID = f'{_MOD}.GOOGLE_SHEETS_ID'
_PATCH_GID = f'{_MOD}.GOOGLE_SHEETS_TW_TRANSACTIONS_GID'


_HEADER = '股名,日期,成交股數,成本,買賣別,淨股數,淨金額,年度\n'


def _make_csv(*rows: str) -> str:
    return _HEADER + '\n'.join(rows)


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ── _parse_number ─────────────────────────────────────────────────────────


def test_parse_number_plain() -> None:
    assert _parse_number('1000') == 1000.0


def test_parse_number_with_comma() -> None:
    assert _parse_number('1,000') == 1000.0


def test_parse_number_negative() -> None:
    assert _parse_number('-75,000') == -75000.0


def test_parse_number_empty() -> None:
    assert _parse_number('') == 0.0


# ── _parse_date ───────────────────────────────────────────────────────────


def test_parse_date_iso_dash() -> None:
    assert _parse_date('2026-04-22') == date(2026, 4, 22)


def test_parse_date_slash() -> None:
    assert _parse_date('2026/04/22') == date(2026, 4, 22)


def test_parse_date_dot() -> None:
    assert _parse_date('2026.04.22') == date(2026, 4, 22)


def test_parse_date_invalid_returns_none() -> None:
    assert _parse_date('not-a-date') is None


def test_parse_date_empty_returns_none() -> None:
    assert _parse_date('') is None


# ── _parse_row ────────────────────────────────────────────────────────────


def test_parse_row_valid_buy() -> None:
    row = ['2330', '2026-04-22', '1000', '820.5', '買', '1000', '-820500', '2026']
    tx = _parse_row(1, row)
    assert tx is not None
    assert tx.symbol == '2330'
    assert tx.date == date(2026, 4, 22)
    assert tx.shares == 1000.0
    assert tx.cost == 820.5
    assert tx.action == '買'
    assert tx.net_shares == 1000.0
    assert tx.net_amount == -820500.0
    assert tx.year == 2026


def test_parse_row_too_short_returns_none() -> None:
    assert _parse_row(1, ['2330', '2026-04-22']) is None


def test_parse_row_unparseable_date_returns_none() -> None:
    row = ['2330', 'garbage', '1000', '820.5', '買', '1000', '-820500', '2026']
    assert _parse_row(1, row) is None


def test_parse_row_empty_symbol_returns_none() -> None:
    row = ['', '2026-04-22', '1000', '820.5', '買', '1000', '-820500', '2026']
    assert _parse_row(1, row) is None


def test_parse_row_empty_year_falls_back_to_date_year() -> None:
    row = ['2330', '2026-04-22', '1000', '820.5', '買', '1000', '-820500', '']
    tx = _parse_row(1, row)
    assert tx is not None
    assert tx.year == 2026


# ── fetch_tw_transactions ─────────────────────────────────────────────────


def test_fetch_tw_transactions_happy_path() -> None:
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5,買,1000,"-820,500",2026',
        '0050,2026/04/15,500,150.0,買,500,"-75,000",2026',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        result = fetch_tw_transactions()

    assert len(result) == 2
    assert result[0].symbol == '2330'
    assert result[1].symbol == '0050'
    assert result[1].date == date(2026, 4, 15)


def test_fetch_tw_transactions_missing_config_returns_empty() -> None:
    with patch(_PATCH_ID, ''), patch(_PATCH_GID, '456'):
        assert fetch_tw_transactions() == []


def test_fetch_tw_transactions_network_error_returns_empty() -> None:
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', side_effect=httpx.RequestError('boom')),
    ):
        assert fetch_tw_transactions() == []


def test_fetch_tw_transactions_http_error_returns_empty() -> None:
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        '404', request=MagicMock(), response=MagicMock()
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=resp),
    ):
        assert fetch_tw_transactions() == []


def test_fetch_tw_transactions_skips_malformed_rows() -> None:
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5,買,1000,-820500,2026',
        'badrow',
        ',2026-04-22,1,1,買,1,-1,2026',
        '0050,2026-04-15,500,150,買,500,-75000,2026',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        result = fetch_tw_transactions()

    assert [tx.symbol for tx in result] == ['2330', '0050']


# ── sum_buy_amount ────────────────────────────────────────────────────────


def test_sum_buy_amount_only_buys_in_window() -> None:
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5,買,1000,"-820,500",2026',
        '0050,2026-04-15,500,150.0,買,500,"-75,000",2026',
        '2454,2026-04-20,100,900,賣,-100,"90,000",2026',  # sell — ignored
        'AAPL,2026-03-31,10,180,買,10,"-1,800",2026',  # wrong month
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        total = sum_buy_amount(2026, 4)

    assert total == 820500.0 + 75000.0


def test_sum_buy_amount_returns_zero_when_no_matches() -> None:
    csv_text = _make_csv('2330,2026-04-22,1000,820,買,1000,-820000,2026')
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        total = sum_buy_amount(2025, 12)

    assert total == 0.0


def test_sum_buy_amount_counts_xian_buy() -> None:
    """'現買' (cash buy) 必須被計入。"""
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5,現買,1000,"-820,500",2026',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        assert sum_buy_amount(2026, 4) == 820500.0


def test_sum_buy_amount_counts_chong_buy() -> None:
    """'沖買' (day-trade buy) 必須被計入。"""
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5,沖買,1000,"-820,500",2026',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        assert sum_buy_amount(2026, 4) == 820500.0


def test_sum_buy_amount_excludes_xian_sell() -> None:
    """'現賣' (cash sell) 必須被排除。"""
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5,現賣,-1000,"820,500",2026',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        assert sum_buy_amount(2026, 4) == 0.0


def test_sum_buy_amount_excludes_chong_sell() -> None:
    """'沖賣' (day-trade sell) 必須被排除。"""
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5,沖賣,-1000,"820,500",2026',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        assert sum_buy_amount(2026, 4) == 0.0


def test_sum_buy_amount_counts_action_with_surrounding_whitespace() -> None:
    """CSV 可能含前後空白 — 經 strip 後仍應視為買入。"""
    csv_text = _make_csv(
        '2330,2026-04-22,1000,820.5, 現買 ,1000,"-820,500",2026',
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        assert sum_buy_amount(2026, 4) == 820500.0


def test_sum_buy_amount_mixed_actions_only_buys_counted() -> None:
    """混合四種買賣別 + 跨月份 — 僅計入當月之 *買 變體。"""
    csv_text = _make_csv(
        '2330,2026-04-01,1000,820,現買,1000,"-820,000",2026',
        '0050,2026-04-05,500,150,沖買,500,"-75,000",2026',
        '2454,2026-04-10,100,900,現賣,-100,"90,000",2026',  # excluded
        '3008,2026-04-15,200,500,沖賣,-200,"100,000",2026',  # excluded
        'AAPL,2026-03-31,10,180,現買,10,"-1,800",2026',  # wrong month
    )
    with (
        patch(_PATCH_ID, '123'),
        patch(_PATCH_GID, '456'),
        patch('httpx.get', return_value=_mock_response(csv_text)),
    ):
        assert sum_buy_amount(2026, 4) == 820000.0 + 75000.0
