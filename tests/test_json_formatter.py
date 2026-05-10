"""Unit tests for the StructuredJsonFormatter (Spec 007, T004)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal

from fastapistock.core.json_formatter import StructuredJsonFormatter


def _make_formatter() -> StructuredJsonFormatter:
    return StructuredJsonFormatter(service='test-svc', environment='test')


def _capture_json(
    formatter: StructuredJsonFormatter,
    msg: str,
    extra: dict[str, object] | None = None,
    level: int = logging.INFO,
) -> dict[str, object]:
    """Emit one log record and return the parsed JSON dict."""
    logger = logging.getLogger('test_json_fmt')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    record = logger.makeRecord(
        name='test_json_fmt',
        level=level,
        fn='test',
        lno=0,
        msg=msg,
        args=(),
        exc_info=None,
        extra=extra,
    )
    raw = formatter.format(record)
    parsed: dict[str, object] = json.loads(raw)
    return parsed


class TestStructuredJsonFormatter:
    def test_service_and_environment_injected(self) -> None:
        fmt = _make_formatter()
        data = _capture_json(fmt, 'hello')
        assert data['service'] == 'test-svc'
        assert data['environment'] == 'test'

    def test_extra_fields_appear_as_top_level_keys(self) -> None:
        fmt = _make_formatter()
        data = _capture_json(
            fmt,
            'PERF',
            extra={
                'log_type': 'PERF',
                'route': 'get_stocks',
                'method': 'GET',
                'status_code': 200,
                'duration_ms': 123,
            },
        )
        assert data['log_type'] == 'PERF'
        assert data['route'] == 'get_stocks'
        assert data['method'] == 'GET'
        assert data['status_code'] == 200
        assert data['duration_ms'] == 123

    def test_duration_ms_is_integer(self) -> None:
        fmt = _make_formatter()
        data = _capture_json(fmt, 'PERF', extra={'duration_ms': int(round(333.7))})
        assert isinstance(data['duration_ms'], int)

    def test_decimal_serialised_as_string(self) -> None:
        fmt = _make_formatter()
        data = _capture_json(fmt, 'decimal', extra={'amount': Decimal('123.45')})
        assert data['amount'] == '123.45'

    def test_datetime_serialised_as_string(self) -> None:
        fmt = _make_formatter()
        dt = datetime(2026, 5, 9, 10, 23, 45)
        data = _capture_json(fmt, 'dt', extra={'captured_at': dt})
        assert '2026-05-09' in str(data['captured_at'])

    def test_job_id_and_trigger_appear(self) -> None:
        fmt = _make_formatter()
        data = _capture_json(
            fmt,
            'report_history.build.start',
            extra={
                'job_id': 'abc12345',
                'trigger': 'cron',
                'report_type': 'weekly',
            },
        )
        assert data['job_id'] == 'abc12345'
        assert data['trigger'] == 'cron'
        assert data['report_type'] == 'weekly'

    def test_error_type_appears(self) -> None:
        fmt = _make_formatter()
        data = _capture_json(
            fmt,
            'fail',
            extra={'error_type': 'SQLAlchemyError', 'duration_ms': 42},
            level=logging.ERROR,
        )
        assert data['error_type'] == 'SQLAlchemyError'
        assert data['duration_ms'] == 42

    def test_output_is_valid_json(self) -> None:
        fmt = _make_formatter()
        logger = logging.getLogger('test_json_valid')
        record = logger.makeRecord(
            name='test_json_valid',
            level=logging.INFO,
            fn='test',
            lno=0,
            msg='check',
            args=(),
            exc_info=None,
        )
        raw = fmt.format(record)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
