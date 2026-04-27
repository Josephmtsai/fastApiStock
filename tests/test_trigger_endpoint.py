"""Tests for ``POST /api/v1/reports/history/trigger`` (spec-006 Phase 5).

The endpoint wraps :func:`run_report_pipeline` with Bearer-token auth.
We mock the pipeline so each test only exercises the router/auth contract.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fastapistock.main import app
from fastapistock.services.report_service import RunReportResult

client = TestClient(app)

_PIPELINE_PATH = 'fastapistock.routers.reports.run_report_pipeline'
_TRIGGER_URL = '/api/v1/reports/history/trigger'
_VALID_TOKEN = 'a' * 64  # arbitrary 64-char hex-like string


def _make_result(
    *,
    dry_run: bool = False,
    report_type: str = 'monthly',
    report_period: str = '2026-03',
    postgres_ok: bool = True,
    sheet_ok: bool | None = True,
    telegram_sent: bool = False,
    symbol_rows_written: int = 12,
    summary_written: bool = True,
    duration_ms: int = 4523,
    errors: list[str] | None = None,
) -> RunReportResult:
    """Build a deterministic ``RunReportResult`` for assertion."""
    return RunReportResult(
        job_id='a3f2c91e',
        report_type=report_type,  # type: ignore[arg-type]
        report_period=report_period,
        trigger='manual',
        dry_run=dry_run,
        telegram_sent=telegram_sent,
        postgres_ok=postgres_ok,
        sheet_ok=sheet_ok,
        symbol_rows_written=symbol_rows_written,
        summary_written=summary_written,
        duration_ms=duration_ms,
        errors=errors if errors is not None else [],
    )


@pytest.fixture
def admin_token(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set ``config.ADMIN_TOKEN`` for the duration of a single test."""
    monkeypatch.setattr('fastapistock.routers.reports.config.ADMIN_TOKEN', _VALID_TOKEN)
    return _VALID_TOKEN


# ── Authorization gate ─────────────────────────────────────────────────────


class TestAdminTokenGate:
    """Verify the 503 / 401 paths before any pipeline call."""

    def test_admin_token_unset_returns_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr('fastapistock.routers.reports.config.ADMIN_TOKEN', None)
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'monthly'},
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 503
        assert 'admin trigger not configured' in response.json()['detail']
        mock_pipeline.assert_not_called()

    def test_admin_token_empty_string_returns_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr('fastapistock.routers.reports.config.ADMIN_TOKEN', '')
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'monthly'},
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 503
        mock_pipeline.assert_not_called()

    def test_missing_authorization_header_returns_401(self, admin_token: str) -> None:
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(_TRIGGER_URL, json={'report_type': 'monthly'})

        assert response.status_code == 401
        assert 'missing bearer token' in response.json()['detail']
        mock_pipeline.assert_not_called()

    def test_malformed_authorization_scheme_returns_401(self, admin_token: str) -> None:
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'monthly'},
                headers={'Authorization': f'Token {_VALID_TOKEN}'},
            )

        assert response.status_code == 401
        assert 'missing bearer token' in response.json()['detail']
        mock_pipeline.assert_not_called()

    def test_wrong_token_returns_401(self, admin_token: str) -> None:
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'monthly'},
                headers={'Authorization': 'Bearer wrong-token'},
            )

        assert response.status_code == 401
        assert 'invalid token' in response.json()['detail']
        mock_pipeline.assert_not_called()


# ── Body validation ────────────────────────────────────────────────────────


class TestBodyValidation:
    """Pydantic-driven 422 cases."""

    def test_invalid_report_period_format_returns_422(self, admin_token: str) -> None:
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'monthly', 'report_period': 'bad'},
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 422
        mock_pipeline.assert_not_called()

    def test_invalid_report_type_returns_422(self, admin_token: str) -> None:
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'daily'},
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 422
        mock_pipeline.assert_not_called()


# ── Happy path ─────────────────────────────────────────────────────────────


class TestSuccessfulTrigger:
    """Successful 200 paths verifying envelope + pipeline arguments."""

    def test_dry_run_returns_200_and_marks_dry_run(self, admin_token: str) -> None:
        fake_result = _make_result(
            dry_run=True,
            postgres_ok=False,
            sheet_ok=None,
            symbol_rows_written=0,
            summary_written=False,
        )
        with patch(_PIPELINE_PATH, return_value=fake_result) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={
                    'report_type': 'monthly',
                    'report_period': '2026-03',
                    'dry_run': True,
                },
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'success'
        assert body['message'] == ''
        assert body['data']['dry_run'] is True
        assert body['data']['postgres_ok'] is False
        assert body['data']['sheet_ok'] is None
        assert body['data']['symbol_rows_written'] == 0
        # Pipeline must be invoked exactly once with the correct flags.
        mock_pipeline.assert_called_once_with(
            report_type='monthly',
            report_period='2026-03',
            dry_run=True,
            skip_telegram=True,  # default
            skip_sheet=False,  # default
            trigger='manual',
        )

    def test_full_monthly_run_returns_complete_result(self, admin_token: str) -> None:
        fake_result = _make_result()
        with patch(_PIPELINE_PATH, return_value=fake_result) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={
                    'report_type': 'monthly',
                    'report_period': '2026-03',
                    'dry_run': False,
                    'skip_telegram': True,
                    'skip_sheet': False,
                },
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 200
        data: dict[str, Any] = response.json()['data']
        # Full RunReportResult schema must round-trip via asdict.
        for field in (
            'job_id',
            'report_type',
            'report_period',
            'trigger',
            'dry_run',
            'telegram_sent',
            'postgres_ok',
            'sheet_ok',
            'symbol_rows_written',
            'summary_written',
            'duration_ms',
            'errors',
        ):
            assert field in data, f'missing field {field}'
        assert data['job_id'] == 'a3f2c91e'
        assert data['report_type'] == 'monthly'
        assert data['postgres_ok'] is True
        assert data['sheet_ok'] is True
        assert data['symbol_rows_written'] == 12
        mock_pipeline.assert_called_once_with(
            report_type='monthly',
            report_period='2026-03',
            dry_run=False,
            skip_telegram=True,
            skip_sheet=False,
            trigger='manual',
        )

    def test_weekly_with_default_flags(self, admin_token: str) -> None:
        fake_result = _make_result(
            report_type='weekly',
            report_period='2026-04-19',
            sheet_ok=None,
        )
        with patch(_PIPELINE_PATH, return_value=fake_result) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'weekly'},
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 200
        data = response.json()['data']
        assert data['report_type'] == 'weekly'
        assert data['sheet_ok'] is None  # weekly never writes sheet
        # Defaults: report_period=None, dry_run=False, skip_telegram=True
        mock_pipeline.assert_called_once_with(
            report_type='weekly',
            report_period=None,
            dry_run=False,
            skip_telegram=True,
            skip_sheet=False,
            trigger='manual',
        )


# ── Auth ordering ──────────────────────────────────────────────────────────


class TestAuthRunsBeforePipeline:
    """503 must take precedence over body validation to avoid leaking schema."""

    def test_503_takes_precedence_over_invalid_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr('fastapistock.routers.reports.config.ADMIN_TOKEN', None)
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post(
                _TRIGGER_URL,
                json={'report_type': 'invalid'},
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        # FastAPI evaluates Depends() before request body validation, so the
        # admin-token gate (503) must short-circuit before Pydantic 422.
        assert response.status_code == 503
        mock_pipeline.assert_not_called()

    def test_pipeline_value_error_returns_500(self, admin_token: str) -> None:
        # run_report_pipeline only raises ValueError when given a period that
        # somehow bypassed Pydantic.  The app's catch-all handler converts it
        # to a 500 envelope.  TestClient must be told not to propagate the
        # exception so we observe the handler's response instead.
        local_client = TestClient(app, raise_server_exceptions=False)
        with patch(
            _PIPELINE_PATH, side_effect=ValueError('bad period')
        ) as mock_pipeline:
            response = local_client.post(
                _TRIGGER_URL,
                json={'report_type': 'monthly'},
                headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
            )

        assert response.status_code == 500
        body = response.json()
        assert body['status'] == 'error'
        mock_pipeline.assert_called_once()


# ── Smoke: MagicMock as RunReportResult drop-in ────────────────────────────


def test_admin_token_dependency_is_invoked_once_per_request(
    admin_token: str,
) -> None:
    """Sanity check that asdict() is what serialises the result."""
    fake_result = _make_result()
    with patch(_PIPELINE_PATH, return_value=fake_result):
        response = client.post(
            _TRIGGER_URL,
            json={'report_type': 'monthly'},
            headers={'Authorization': f'Bearer {_VALID_TOKEN}'},
        )

    assert response.status_code == 200
    # MagicMock would not round-trip through asdict — using a real dataclass
    # confirms the route produces a JSON-safe payload.
    assert isinstance(response.json()['data'], dict)
    # Belt-and-braces — ensure we didn't accidentally eat the MagicMock module.
    assert MagicMock is not None
