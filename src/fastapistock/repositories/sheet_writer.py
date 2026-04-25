"""Google Sheets archive writer for monthly portfolio history (spec-006 B).

Append per-symbol monthly snapshots to the configured TW / US worksheet tabs.
Failure of this writer must never block the main report pipeline; every error
is logged at WARNING and the function returns ``False`` instead of raising.

Service Account credentials are loaded from ``GOOGLE_SERVICE_ACCOUNT_B64``
(preferred, base64-encoded JSON) or ``GOOGLE_SERVICE_ACCOUNT_JSON`` (raw
JSON string).  When neither is set the module logs once at WARNING and the
writer is treated as disabled.

Sheet layout (per spec functionality B)::

    report_period | symbol | shares | avg_cost | current_price | market_value |
    unrealized_pnl | pnl_pct | pnl_delta | captured_at(ISO 8601)
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread.utils import ValueInputOption

from fastapistock import config
from fastapistock.repositories.report_history_repo import SymbolSnapshot

if TYPE_CHECKING:
    from gspread.worksheet import Worksheet

logger = logging.getLogger('fastapistock.report_history')

_SCOPES: tuple[str, ...] = ('https://www.googleapis.com/auth/spreadsheets',)
_REPORT_PERIOD_COL_INDEX: int = 1  # 1-based column index of report_period
_NULL_CELL_PLACEHOLDER: str = '-'  # rendered for missing pnl_pct / pnl_delta


def _load_service_account_info() -> dict[str, Any] | None:
    """Load Service Account credentials from env, preferring B64 encoding.

    Returns:
        Parsed credentials dict, or ``None`` when neither env var is set
        (caller logs the disabled state).

    Note:
        ``Any`` is unavoidable here because the service-account JSON is a
        free-form payload consumed by ``gspread`` / ``google-auth``.
    """
    b64 = config.GOOGLE_SERVICE_ACCOUNT_B64
    if b64:
        try:
            decoded = base64.b64decode(b64)
            payload: dict[str, Any] = json.loads(decoded)
            return payload
        except (binascii.Error, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                'report_history.sheet.credentials.b64_decode_fail',
                extra={'error_type': type(exc).__name__, 'error_message': str(exc)},
            )
            return None
    raw = config.GOOGLE_SERVICE_ACCOUNT_JSON
    if raw:
        try:
            payload_json: dict[str, Any] = json.loads(raw)
            return payload_json
        except json.JSONDecodeError as exc:
            logger.warning(
                'report_history.sheet.credentials.json_parse_fail',
                extra={'error_type': type(exc).__name__, 'error_message': str(exc)},
            )
            return None
    return None


def _resolve_gid(market: str) -> int | None:
    """Return the configured worksheet GID for the given market.

    Args:
        market: ``'TW'`` or ``'US'``.

    Returns:
        Worksheet ``gid`` integer, or ``None`` when the market is unknown
        or no env var was supplied.
    """
    if market == 'TW':
        return config.GOOGLE_SHEETS_HISTORY_GID_TW
    if market == 'US':
        return config.GOOGLE_SHEETS_HISTORY_GID_US
    return None


def _decimal_cell(value: Decimal | None) -> str | float:
    """Convert a ``Decimal`` to a Sheets-compatible cell value.

    ``None`` becomes :data:`_NULL_CELL_PLACEHOLDER` (a single dash) so the
    row keeps its column count and renders with an obvious "no data" marker;
    otherwise the value is cast to ``float`` (Sheets API rejects Decimal).
    """
    return float(value) if value is not None else _NULL_CELL_PLACEHOLDER


def _row_to_sheet_values(row: SymbolSnapshot) -> list[str | float]:
    """Project a snapshot to the column order required by the Sheet."""
    return [
        row.report_period,
        row.symbol,
        _decimal_cell(row.shares),
        _decimal_cell(row.avg_cost),
        _decimal_cell(row.current_price),
        _decimal_cell(row.market_value),
        _decimal_cell(row.unrealized_pnl),
        _decimal_cell(row.pnl_pct),
        _decimal_cell(row.pnl_delta),
        row.captured_at.isoformat(),
    ]


def _find_worksheet_by_gid(
    spreadsheet: gspread.Spreadsheet, gid: int
) -> Worksheet | None:
    """Locate a worksheet by ``gid`` within a spreadsheet.

    Args:
        spreadsheet: Already-opened gspread Spreadsheet.
        gid: Numeric worksheet identifier (from URL ``#gid=…``).

    Returns:
        Matching ``Worksheet`` or ``None`` when not found.
    """
    for ws in spreadsheet.worksheets():
        if ws.id == gid:
            return ws
    return None


def _delete_existing_period_rows(worksheet: Worksheet, report_period: str) -> int:
    """Delete every row whose ``report_period`` (column A) matches.

    Idempotency helper: callers run this before appending a fresh batch so
    re-runs of the same monthly period don't duplicate rows.

    Args:
        worksheet: Target sheet tab.
        report_period: Period string to match (e.g. ``'2026-04'``).

    Returns:
        Number of rows deleted.
    """
    existing = worksheet.col_values(_REPORT_PERIOD_COL_INDEX)
    # ``col_values`` returns top-down including the header row; iterate from
    # the bottom so row indices stay stable while we delete.
    deleted = 0
    for row_idx in range(len(existing), 0, -1):
        if existing[row_idx - 1] == report_period:
            worksheet.delete_rows(row_idx)
            deleted += 1
    return deleted


def append_monthly_history(market: str, rows: list[SymbolSnapshot]) -> bool:
    """Append per-symbol monthly snapshots to the market-specific worksheet.

    Behaviour:
        * Loads credentials lazily; no-credentials path returns ``False``.
        * Idempotent: rows for the same ``report_period`` are deleted first.
        * Never raises — any error is logged and ``False`` is returned.

    Args:
        market: ``'TW'`` or ``'US'``; selects which GID env var to use.
        rows: Snapshots to append (must all share one ``report_period``).

    Returns:
        ``True`` when the rows were appended successfully, ``False`` otherwise.
    """
    if not rows:
        logger.info('report_history.sheet.append.skip_empty', extra={'market': market})
        return False

    info = _load_service_account_info()
    if info is None:
        logger.warning(
            'report_history.sheet.disabled',
            extra={'reason': 'service_account_not_configured', 'market': market},
        )
        return False

    sheet_id = config.GOOGLE_SHEETS_HISTORY_ID
    if not sheet_id:
        logger.warning(
            'report_history.sheet.disabled',
            extra={'reason': 'history_sheet_id_missing', 'market': market},
        )
        return False

    gid = _resolve_gid(market)
    if gid is None:
        logger.warning(
            'report_history.sheet.append.fail',
            extra={
                'market': market,
                'error_type': 'ConfigError',
                'error_message': f'No GID configured for market={market!r}',
            },
        )
        return False

    report_period = rows[0].report_period
    logger.info(
        'report_history.sheet.append.start',
        extra={'market': market, 'gid': gid, 'rows': len(rows)},
    )

    try:
        client = gspread.service_account_from_dict(info, scopes=list(_SCOPES))
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = _find_worksheet_by_gid(spreadsheet, gid)
        if worksheet is None:
            logger.warning(
                'report_history.sheet.append.fail',
                extra={
                    'market': market,
                    'gid': gid,
                    'error_type': 'WorksheetNotFound',
                    'error_message': f'gid={gid} not present in sheet={sheet_id}',
                },
            )
            return False

        deleted = _delete_existing_period_rows(worksheet, report_period)
        values = [_row_to_sheet_values(row) for row in rows]
        worksheet.append_rows(values, value_input_option=ValueInputOption.user_entered)
    except (APIError, SpreadsheetNotFound, WorksheetNotFound) as exc:
        logger.warning(
            'report_history.sheet.append.fail',
            extra={
                'market': market,
                'gid': gid,
                'error_type': type(exc).__name__,
                'error_message': str(exc),
            },
        )
        return False
    except Exception as exc:  # defensive: never bubble to the report pipeline
        logger.warning(
            'report_history.sheet.append.fail',
            extra={
                'market': market,
                'gid': gid,
                'error_type': type(exc).__name__,
                'error_message': str(exc),
            },
        )
        return False

    logger.info(
        'report_history.sheet.append.ok',
        extra={
            'market': market,
            'gid': gid,
            'rows': len(rows),
            'deleted_existing': deleted,
        },
    )
    return True
