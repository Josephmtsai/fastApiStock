"""Unit tests for fastapistock.repositories.sheet_writer (spec-006 B)."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from gspread.exceptions import APIError

from fastapistock.repositories import sheet_writer
from fastapistock.repositories.report_history_repo import SymbolSnapshot

_TZ = ZoneInfo('Asia/Taipei')

_FAKE_CREDS: dict[str, Any] = {
    'type': 'service_account',
    'project_id': 'fake',
    'private_key': 'fake-pem-content-for-tests-only',
    'client_email': 'svc@fake.iam.gserviceaccount.com',
}


def _snapshot(
    *,
    report_period: str = '2026-04',
    market: str = 'TW',
    symbol: str = '2330',
) -> SymbolSnapshot:
    return SymbolSnapshot(
        report_type='monthly',
        report_period=report_period,
        market=market,
        symbol=symbol,
        shares=Decimal('1000'),
        avg_cost=Decimal('750.5'),
        current_price=Decimal('820.0'),
        market_value=Decimal('820000.00'),
        unrealized_pnl=Decimal('69500.00'),
        pnl_pct=Decimal('9.2594'),
        pnl_delta=Decimal('15000.00'),
        captured_at=datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )


# ---------------------------------------------------------------------------
# _load_service_account_info
# ---------------------------------------------------------------------------


def test_load_service_account_info_b64_takes_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_payload = {'kind': 'b64'}
    encoded = base64.b64encode(json.dumps(raw_payload).encode('utf-8')).decode('ascii')
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_B64', encoded)
    monkeypatch.setattr(
        sheet_writer.config,
        'GOOGLE_SERVICE_ACCOUNT_JSON',
        json.dumps({'kind': 'json'}),
    )

    info = sheet_writer._load_service_account_info()
    assert info == raw_payload


def test_load_service_account_info_falls_back_to_raw_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_B64', None)
    monkeypatch.setattr(
        sheet_writer.config,
        'GOOGLE_SERVICE_ACCOUNT_JSON',
        json.dumps({'kind': 'json'}),
    )

    info = sheet_writer._load_service_account_info()
    assert info == {'kind': 'json'}


def test_load_service_account_info_returns_none_when_both_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_B64', None)
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_JSON', None)
    assert sheet_writer._load_service_account_info() is None


def test_load_service_account_info_b64_invalid_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_B64', 'not!!!base64!!!'
    )
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_JSON', None)
    assert sheet_writer._load_service_account_info() is None


def test_load_service_account_info_raw_json_invalid_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_B64', None)
    monkeypatch.setattr(
        sheet_writer.config, 'GOOGLE_SERVICE_ACCOUNT_JSON', '{not valid json'
    )
    assert sheet_writer._load_service_account_info() is None


# ---------------------------------------------------------------------------
# Helpers for building a fully mocked gspread stack
# ---------------------------------------------------------------------------


def _install_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sheet_writer, '_load_service_account_info', lambda: _FAKE_CREDS)


def _patch_gspread(
    monkeypatch: pytest.MonkeyPatch,
    *,
    worksheet: MagicMock | None = None,
    worksheets: list[MagicMock] | None = None,
    open_side_effect: Exception | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Patch gspread.service_account_from_dict and return (client, spreadsheet)."""
    spreadsheet = MagicMock(name='Spreadsheet')
    if worksheets is None:
        worksheets = [worksheet] if worksheet is not None else []
    spreadsheet.worksheets.return_value = worksheets

    client = MagicMock(name='Client')
    if open_side_effect is not None:
        client.open_by_key.side_effect = open_side_effect
    else:
        client.open_by_key.return_value = spreadsheet

    monkeypatch.setattr(
        sheet_writer.gspread, 'service_account_from_dict', lambda *a, **kw: client
    )
    return client, spreadsheet


def _install_history_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sheet_id: str | None = 'sheet-abc',
    gid_tw: int | None = 151284230,
    gid_us: int | None = 448638367,
) -> None:
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SHEETS_HISTORY_ID', sheet_id)
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SHEETS_HISTORY_GID_TW', gid_tw)
    monkeypatch.setattr(sheet_writer.config, 'GOOGLE_SHEETS_HISTORY_GID_US', gid_us)


# ---------------------------------------------------------------------------
# append_monthly_history
# ---------------------------------------------------------------------------


def test_append_monthly_history_no_credentials_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sheet_writer, '_load_service_account_info', lambda: None)
    _install_history_config(monkeypatch)

    assert sheet_writer.append_monthly_history('TW', [_snapshot()]) is False


def test_append_monthly_history_empty_rows_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch)
    assert sheet_writer.append_monthly_history('TW', []) is False


def test_append_monthly_history_no_sheet_id_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch, sheet_id=None)
    assert sheet_writer.append_monthly_history('TW', [_snapshot()]) is False


def test_append_monthly_history_unknown_market_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch)
    assert sheet_writer.append_monthly_history('JP', [_snapshot(market='JP')]) is False


def test_append_monthly_history_missing_gid_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch, gid_tw=None)
    assert sheet_writer.append_monthly_history('TW', [_snapshot()]) is False


def test_append_monthly_history_worksheet_not_found_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch)

    # Sheet exists but no worksheet matches the configured GID.
    other_ws = MagicMock(name='OtherWorksheet')
    other_ws.id = 999_999
    _patch_gspread(monkeypatch, worksheets=[other_ws])

    assert sheet_writer.append_monthly_history('TW', [_snapshot()]) is False
    other_ws.append_rows.assert_not_called()


def test_append_monthly_history_success_appends_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch)

    ws = MagicMock(name='Worksheet')
    ws.id = 151284230
    # No pre-existing rows for this period.
    ws.col_values.return_value = ['report_period']  # only header
    _patch_gspread(monkeypatch, worksheet=ws)

    rows = [_snapshot(symbol='2330'), _snapshot(symbol='0050')]
    result = sheet_writer.append_monthly_history('TW', rows)

    assert result is True
    ws.append_rows.assert_called_once()
    appended_values = ws.append_rows.call_args.args[0]
    assert len(appended_values) == 2
    # First column (report_period) and second column (symbol) verified.
    assert [r[0] for r in appended_values] == ['2026-04', '2026-04']
    assert [r[1] for r in appended_values] == ['2330', '0050']
    # captured_at projected as ISO 8601 string (last column).
    assert appended_values[0][-1] == '2026-05-01T21:00:00+08:00'
    ws.delete_rows.assert_not_called()


def test_append_monthly_history_idempotent_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch)

    ws = MagicMock(name='Worksheet')
    ws.id = 151284230
    # Two old rows for the same period exist (rows 2 and 4).
    ws.col_values.return_value = [
        'report_period',
        '2026-04',
        '2026-03',
        '2026-04',
    ]
    _patch_gspread(monkeypatch, worksheet=ws)

    result = sheet_writer.append_monthly_history('TW', [_snapshot()])

    assert result is True
    # delete_rows must be called for both row 2 and row 4 (descending order).
    deleted_indices = [c.args[0] for c in ws.delete_rows.call_args_list]
    assert deleted_indices == [4, 2]
    ws.append_rows.assert_called_once()


def test_append_monthly_history_api_error_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch)

    ws = MagicMock(name='Worksheet')
    ws.id = 151284230
    ws.col_values.return_value = ['report_period']

    response = MagicMock()
    response.json.return_value = {'error': {'code': 500, 'message': 'boom'}}
    response.status_code = 500
    response.text = 'boom'
    ws.append_rows.side_effect = APIError(response)

    _patch_gspread(monkeypatch, worksheet=ws)

    result = sheet_writer.append_monthly_history('TW', [_snapshot()])
    assert result is False


def test_append_monthly_history_renders_none_pnl_as_dash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pnl_pct`` / ``pnl_delta`` of ``None`` must serialise to ``'-'``.

    Regression: the writer previously rendered missing values as the empty
    string, which produced confusing blank cells in the archive. The marker
    is a single dash so users can distinguish "no data" from a zero value.
    """
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch)

    ws = MagicMock(name='Worksheet')
    ws.id = 151284230
    ws.col_values.return_value = ['report_period']
    _patch_gspread(monkeypatch, worksheet=ws)

    snap = SymbolSnapshot(
        report_type='monthly',
        report_period='2026-04',
        market='TW',
        symbol='2330',
        shares=Decimal('1000'),
        avg_cost=Decimal('750.5'),
        current_price=Decimal('820.0'),
        market_value=Decimal('820000.00'),
        unrealized_pnl=Decimal('69500.00'),
        pnl_pct=None,
        pnl_delta=None,
        captured_at=datetime(2026, 5, 1, 21, 0, tzinfo=_TZ),
    )

    assert sheet_writer.append_monthly_history('TW', [snap]) is True
    appended = ws.append_rows.call_args.args[0]
    # Layout: [period, symbol, shares, avg_cost, current_price, market_value,
    #          unrealized_pnl, pnl_pct, pnl_delta, captured_at]
    assert appended[0][7] == '-'
    assert appended[0][8] == '-'


def test_append_monthly_history_us_market_uses_us_gid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_credentials(monkeypatch)
    _install_history_config(monkeypatch, gid_tw=111, gid_us=222)

    ws_tw = MagicMock(name='WorksheetTW')
    ws_tw.id = 111
    ws_us = MagicMock(name='WorksheetUS')
    ws_us.id = 222
    ws_us.col_values.return_value = ['report_period']
    _patch_gspread(monkeypatch, worksheets=[ws_tw, ws_us])

    rows = [_snapshot(market='US', symbol='AAPL')]
    assert sheet_writer.append_monthly_history('US', rows) is True

    ws_us.append_rows.assert_called_once()
    ws_tw.append_rows.assert_not_called()
