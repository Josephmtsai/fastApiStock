"""Integration tests for the reports router (/api/v1/reports/*).

These tests cover:
    - Preview endpoints return rendered text and never call Telegram.
    - Send endpoints invoke the Telegram dispatch layer.
    - The dedicated /api/v1/reports rate-limit bucket returns HTTP 429.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from fastapistock.main import app

client = TestClient(app)

_MD_SEND_PATH = 'fastapistock.services.report_service._send_markdown'
_BUILD_WEEKLY_PATH = 'fastapistock.routers.reports.build_weekly_report'
_BUILD_MONTHLY_PATH = 'fastapistock.routers.reports.build_monthly_report'
_PIPELINE_PATH = 'fastapistock.routers.reports.run_report_pipeline'


# ── Preview endpoints ──────────────────────────────────────────────────────


class TestWeeklyPreview:
    def test_returns_envelope_with_text(self) -> None:
        # build_weekly_report now returns (markdown, fetch_results) — only
        # the markdown reaches the response.
        with (
            patch(
                _BUILD_WEEKLY_PATH,
                return_value=('weekly body md', MagicMock()),
            ) as mock_build,
            patch(_MD_SEND_PATH) as mock_send,
        ):
            response = client.get('/api/v1/reports/weekly/preview')

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'success'
        assert body['message'] == ''
        assert body['data'] == {'text': 'weekly body md'}
        mock_build.assert_called_once()
        # Telegram dispatch must never fire on preview
        mock_send.assert_not_called()


class TestMonthlyPreview:
    def test_returns_envelope_with_text(self) -> None:
        with (
            patch(
                _BUILD_MONTHLY_PATH,
                return_value=('monthly body md', MagicMock()),
            ) as mock_build,
            patch(_MD_SEND_PATH) as mock_send,
        ):
            response = client.get('/api/v1/reports/monthly/preview')

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'success'
        assert body['data'] == {'text': 'monthly body md'}
        mock_build.assert_called_once()
        mock_send.assert_not_called()


# ── Send endpoints ─────────────────────────────────────────────────────────


class TestWeeklySend:
    def test_dispatches_weekly_report(self) -> None:
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post('/api/v1/reports/weekly/send')

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'success'
        assert body['message'] == 'weekly report dispatched'
        mock_pipeline.assert_called_once_with(report_type='weekly', trigger='manual')


class TestMonthlySend:
    def test_dispatches_monthly_report(self) -> None:
        with patch(_PIPELINE_PATH) as mock_pipeline:
            response = client.post('/api/v1/reports/monthly/send')

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'success'
        assert body['message'] == 'monthly report dispatched'
        mock_pipeline.assert_called_once_with(report_type='monthly', trigger='manual')


# ── Rate limit ─────────────────────────────────────────────────────────────


class TestReportsRateLimit:
    """Verify the dedicated /api/v1/reports rate-limit bucket is wired up."""

    def test_preview_rate_limited_returns_429(self) -> None:
        fake_limiter = MagicMock()
        fake_limiter.is_rate_limited.return_value = True
        fake_limiter._config = MagicMock(block_seconds=600)
        with patch('fastapistock.main.get_limiter', return_value=fake_limiter):
            response = client.get('/api/v1/reports/weekly/preview')

        assert response.status_code == 429
        body = response.json()
        assert body['status'] == 'error'
        assert 'Too many requests' in body['message']

    def test_send_rate_limited_returns_429(self) -> None:
        fake_limiter = MagicMock()
        fake_limiter.is_rate_limited.return_value = True
        fake_limiter._config = MagicMock(block_seconds=600)
        with patch('fastapistock.main.get_limiter', return_value=fake_limiter):
            response = client.post('/api/v1/reports/monthly/send')

        assert response.status_code == 429
        assert response.json()['status'] == 'error'
