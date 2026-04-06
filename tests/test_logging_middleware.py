"""Unit tests for the structured logging middleware."""

import logging

import pytest
from fastapi.testclient import TestClient

from fastapistock.main import app

client = TestClient(app)


@pytest.fixture()
def log_records(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Capture log output at INFO level for the middleware logger."""
    with caplog.at_level(logging.INFO, logger='fastapistock.middleware.logging'):
        yield caplog


class TestLoggingMiddleware:
    def test_req_line_emitted(self, log_records: pytest.LogCaptureFixture) -> None:
        client.get('/health')
        messages = [r.message for r in log_records.records]
        assert any('REQ' in m for m in messages)

    def test_res_line_emitted(self, log_records: pytest.LogCaptureFixture) -> None:
        client.get('/health')
        messages = [r.message for r in log_records.records]
        assert any('RES' in m for m in messages)

    def test_perf_line_emitted(self, log_records: pytest.LogCaptureFixture) -> None:
        client.get('/health')
        messages = [r.message for r in log_records.records]
        assert any('PERF' in m for m in messages)

    def test_three_lines_per_request(
        self, log_records: pytest.LogCaptureFixture
    ) -> None:
        log_records.records.clear()
        client.get('/health')
        messages = [r.message for r in log_records.records]
        assert sum(1 for m in messages if 'REQ' in m) >= 1
        assert sum(1 for m in messages if 'RES' in m) >= 1
        assert sum(1 for m in messages if 'PERF' in m) >= 1

    def test_res_contains_status_code(
        self, log_records: pytest.LogCaptureFixture
    ) -> None:
        client.get('/health')
        res_lines = [r.message for r in log_records.records if 'RES' in r.message]
        assert any('200' in m for m in res_lines)

    def test_sensitive_fields_are_masked(
        self, log_records: pytest.LogCaptureFixture
    ) -> None:
        client.get('/health?token=super_secret')
        # Only check records from our middleware, not httpx which logs the raw URL.
        mw_messages = ' '.join(
            r.message
            for r in log_records.records
            if r.name == 'fastapistock.middleware.logging'
        )
        assert 'super_secret' not in mw_messages
        assert '***' in mw_messages
