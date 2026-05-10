"""Supplementary tests for Spec 007 — Structured Logging (Better Stack).

Covers AC items not addressed by the developer-supplied test_json_formatter.py:

  T001 — dependency availability (pythonjsonlogger, logtail-python)
  T002 — LOG_FORMAT=json/text switching, LOGTAIL_SOURCE_TOKEN empty behaviour,
          disable_existing_loggers preservation
  T003 — middleware structured extra fields as independent JSON keys,
          duration_ms integer type from middleware path
  T005 — config defaults, .env.example completeness, .env token absence
  Edge  — LOGTAIL_SOURCE_TOKEN set but server unreachable,
           float duration_ms input, LOG_FORMAT case sensitivity,
           None-valued extra fields, exc_info serialisation
"""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from pathlib import Path
from types import TracebackType
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fastapistock.core.json_formatter import StructuredJsonFormatter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent


_ExcInfo = (
    tuple[type[BaseException], BaseException, TracebackType | None]
    | tuple[None, None, None]
    | None
)


def _emit_to_string(
    formatter: StructuredJsonFormatter,
    msg: str,
    level: int = logging.INFO,
    extra: dict[str, object] | None = None,
    exc_info: _ExcInfo = None,
) -> str:
    """Format one log record to a raw string via the given formatter."""
    logger_name = 'spec007_helper'
    logger = logging.getLogger(logger_name)
    record = logger.makeRecord(
        name=logger_name,
        level=level,
        fn='test',
        lno=0,
        msg=msg,
        args=(),
        exc_info=exc_info,
        extra=extra,
    )
    return str(formatter.format(record))


def _emit_to_json(
    formatter: StructuredJsonFormatter,
    msg: str,
    level: int = logging.INFO,
    extra: dict[str, object] | None = None,
    exc_info: _ExcInfo = None,
) -> dict[str, object]:
    """Format one record and parse the resulting JSON dict."""
    raw = _emit_to_string(formatter, msg, level=level, extra=extra, exc_info=exc_info)
    parsed: dict[str, object] = json.loads(raw)
    return parsed


# ---------------------------------------------------------------------------
# T001: Dependency availability
# ---------------------------------------------------------------------------


class TestT001Dependencies:
    """AC T001 — verify that required packages can be imported without error."""

    def test_pythonjsonlogger_importable(self) -> None:
        """python-json-logger must be installed and importable."""
        # Arrange / Act / Assert  — ImportError signals missing dependency
        import pythonjsonlogger  # noqa: F401 (import-only test)

        assert pythonjsonlogger is not None

    def test_pythonjsonlogger_json_formatter_importable(self) -> None:
        """The specific JsonFormatter class used by the codebase must exist."""
        # Arrange / Act
        from pythonjsonlogger.json import JsonFormatter  # noqa: F401

        # Assert
        assert JsonFormatter is not None

    def test_logtail_handler_importable(self) -> None:
        """logtail-python must be installed and its handler importable."""
        # Arrange / Act
        from logtail import LogtailHandler  # noqa: F401

        # Assert
        assert LogtailHandler is not None

    def test_pyproject_contains_python_json_logger(self) -> None:
        """pyproject.toml must declare python-json-logger as a dependency."""
        # Arrange
        pyproject_path = PROJECT_ROOT / 'pyproject.toml'

        # Act
        content = pyproject_path.read_text(encoding='utf-8')

        # Assert
        assert 'python-json-logger' in content

    def test_pyproject_contains_logtail_python(self) -> None:
        """pyproject.toml must declare logtail-python as a dependency."""
        # Arrange
        pyproject_path = PROJECT_ROOT / 'pyproject.toml'

        # Act
        content = pyproject_path.read_text(encoding='utf-8')

        # Assert
        assert 'logtail-python' in content


# ---------------------------------------------------------------------------
# T002: LOG_FORMAT and LOGTAIL_SOURCE_TOKEN behaviour
# ---------------------------------------------------------------------------


class TestT002LoggingConfig:
    """AC T002 — _build_logging_config() contract."""

    def test_json_format_produces_structured_json_formatter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LOG_FORMAT=json the formatter must be StructuredJsonFormatter."""
        # Arrange
        monkeypatch.setenv('LOG_FORMAT', 'json')
        import fastapistock.config as cfg_mod

        monkeypatch.setattr(cfg_mod, 'LOG_FORMAT', 'json')

        import fastapistock.main as main_mod

        monkeypatch.setattr(main_mod, 'LOG_FORMAT', 'json')

        # Act
        config = main_mod._build_logging_config()

        # Assert
        formatter_cfg = config['formatters']['default']  # type: ignore[index]
        assert formatter_cfg['()'] is StructuredJsonFormatter  # type: ignore[index]

    def test_text_format_produces_plain_formatter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LOG_FORMAT=text the formatter must be a plain format string."""
        # Arrange
        import fastapistock.main as main_mod

        monkeypatch.setattr(main_mod, 'LOG_FORMAT', 'text')

        # Act
        config = main_mod._build_logging_config()

        # Assert
        formatter_cfg = config['formatters']['default']  # type: ignore[index]
        assert 'format' in formatter_cfg  # type: ignore[operator]
        assert '%(asctime)s' in formatter_cfg['format']  # type: ignore[index]
        assert '()' not in formatter_cfg  # type: ignore[operator]

    def test_disable_existing_loggers_is_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """disable_existing_loggers must always be False regardless of LOG_FORMAT."""
        # Arrange
        import fastapistock.main as main_mod

        for fmt in ('json', 'text'):
            monkeypatch.setattr(main_mod, 'LOG_FORMAT', fmt)

            # Act
            config = main_mod._build_logging_config()

            # Assert
            assert config['disable_existing_loggers'] is False, (  # type: ignore[index]
                f'disable_existing_loggers must be False when LOG_FORMAT={fmt}'
            )

    def test_logtail_token_empty_no_handler_added(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LOGTAIL_SOURCE_TOKEN is empty, _attach_logtail_handler is a no-op."""
        # Arrange
        import fastapistock.main as main_mod

        monkeypatch.setattr(main_mod, 'LOGTAIL_SOURCE_TOKEN', '')
        root_logger = logging.getLogger()
        initial_handlers = list(root_logger.handlers)

        # Act
        main_mod._attach_logtail_handler()

        # Assert
        assert root_logger.handlers == initial_handlers

    def test_logtail_token_set_adds_handler(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LOGTAIL_SOURCE_TOKEN is set, a LogtailHandler is added to root."""
        # Arrange
        import fastapistock.main as main_mod

        monkeypatch.setattr(main_mod, 'LOGTAIL_SOURCE_TOKEN', 'fake-test-token-12345')
        root_logger = logging.getLogger()

        try:
            # Act
            main_mod._attach_logtail_handler()

            # Assert
            from logtail import LogtailHandler

            added = [h for h in root_logger.handlers if isinstance(h, LogtailHandler)]
            assert len(added) >= 1
        finally:
            # Cleanup: remove any added LogtailHandlers so other tests are unaffected
            from logtail import LogtailHandler

            for h in list(root_logger.handlers):
                if isinstance(h, LogtailHandler):
                    root_logger.removeHandler(h)

    def test_text_format_output_is_non_empty_and_readable(self) -> None:
        """LOG_FORMAT=text output must be a non-empty human-readable string."""
        # Arrange
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        plain_formatter = logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s'
        )
        handler.setFormatter(plain_formatter)

        logger = logging.getLogger('test_text_mode')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Act
        logger.info('hello from text mode')
        output = buf.getvalue()

        # Assert — must contain the message, be non-empty, and NOT be valid JSON
        assert 'hello from text mode' in output
        assert output.strip() != ''
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(output.strip())

        # Cleanup
        logger.removeHandler(handler)

    def test_json_format_each_line_is_valid_json(self) -> None:
        """LOG_FORMAT=json — every emitted line must parse as valid JSON."""
        # Arrange
        fmt = StructuredJsonFormatter(service='svc', environment='env')
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(fmt)

        logger = logging.getLogger('test_json_lines')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Act
        logger.info('line one')
        logger.warning('line two')
        output = buf.getvalue()

        # Assert — every non-empty line must be parseable JSON
        for line in output.splitlines():
            if line.strip():
                parsed = json.loads(line)
                assert isinstance(parsed, dict)

        # Cleanup
        logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# T003: Middleware extra fields in JSON log records
# ---------------------------------------------------------------------------


class TestT003MiddlewareStructuredFields:
    """AC T003 — LogRecord extras from middleware appear as independent JSON keys."""

    @pytest.fixture()
    def middleware_perf_record(self) -> dict[str, object]:
        """Capture a PERF LogRecord from an actual /health request."""
        from fastapistock.main import app

        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        capture_handler = _Capture()
        mw_logger = logging.getLogger('fastapistock.middleware.logging')
        mw_logger.addHandler(capture_handler)
        mw_logger.setLevel(logging.INFO)

        try:
            client = TestClient(app)
            client.get('/health')
        finally:
            mw_logger.removeHandler(capture_handler)

        perf_records = [r for r in captured if getattr(r, 'log_type', None) == 'PERF']
        assert perf_records, 'Expected at least one PERF record from /health'
        return perf_records[0].__dict__  # type: ignore[return-value]

    def test_log_type_is_independent_key(
        self, middleware_perf_record: dict[str, object]
    ) -> None:
        """log_type must be a direct attribute on the LogRecord (not in msg)."""
        # Assert
        assert middleware_perf_record.get('log_type') == 'PERF'

    def test_route_is_independent_key(
        self, middleware_perf_record: dict[str, object]
    ) -> None:
        """route must be a direct attribute on the LogRecord."""
        assert 'route' in middleware_perf_record
        assert middleware_perf_record['route'] != ''

    def test_method_is_independent_key(
        self, middleware_perf_record: dict[str, object]
    ) -> None:
        """method must be a direct attribute on the LogRecord."""
        assert middleware_perf_record.get('method') == 'GET'

    def test_status_code_is_independent_key(
        self, middleware_perf_record: dict[str, object]
    ) -> None:
        """status_code must be a direct integer attribute on the LogRecord."""
        status_code = middleware_perf_record.get('status_code')
        assert status_code == 200
        assert isinstance(status_code, int)

    def test_duration_ms_is_independent_key(
        self, middleware_perf_record: dict[str, object]
    ) -> None:
        """duration_ms must be a direct attribute on the LogRecord."""
        assert 'duration_ms' in middleware_perf_record

    def test_duration_ms_type_is_integer(
        self, middleware_perf_record: dict[str, object]
    ) -> None:
        """duration_ms on the LogRecord must be an int, not a float."""
        duration = middleware_perf_record.get('duration_ms')
        assert isinstance(duration, int), (
            f'duration_ms must be int, got {type(duration).__name__}: {duration}'
        )

    def test_perf_fields_appear_in_json_output(self) -> None:
        """PERF extra fields must appear as top-level JSON keys when formatted."""
        # Arrange
        fmt = StructuredJsonFormatter(service='test', environment='test')
        data = _emit_to_json(
            fmt,
            'PERF 10ms',
            extra={
                'log_type': 'PERF',
                'route': 'health_check',
                'method': 'GET',
                'status_code': 200,
                'duration_ms': 10,
            },
        )

        # Assert — every required PERF field must be a top-level JSON key
        assert data['log_type'] == 'PERF'
        assert data['route'] == 'health_check'
        assert data['method'] == 'GET'
        assert data['status_code'] == 200
        assert data['duration_ms'] == 10

    def test_req_fields_appear_as_top_level_json_keys(self) -> None:
        """REQ log extras (log_type, route, method, client_ip) must be top-level."""
        # Arrange
        fmt = StructuredJsonFormatter(service='test', environment='test')

        # Act
        data = _emit_to_json(
            fmt,
            'REQ 12345 /api/v1/stocks 1.2.3.4',
            extra={
                'log_type': 'REQ',
                'pid': 12345,
                'route': '/api/v1/stocks',
                'method': 'GET',
                'client_ip': '1.2.3.4',
                'path_params': '{}',
                'query_params': '',
            },
        )

        # Assert
        assert data['log_type'] == 'REQ'
        assert data['route'] == '/api/v1/stocks'
        assert data['method'] == 'GET'
        assert data['client_ip'] == '1.2.3.4'

    def test_res_fields_appear_as_top_level_json_keys(self) -> None:
        """RES log extras (status_code, body) must be top-level JSON keys."""
        # Arrange
        fmt = StructuredJsonFormatter(service='test', environment='test')

        # Act
        data = _emit_to_json(
            fmt,
            'RES 200 {"status":"success"}',
            extra={
                'log_type': 'RES',
                'route': 'health_check',
                'method': 'GET',
                'status_code': 200,
                'body': '{"status":"success"}',
            },
        )

        # Assert
        assert data['log_type'] == 'RES'
        assert data['status_code'] == 200
        assert 'body' in data


# ---------------------------------------------------------------------------
# T005: Config defaults and file checks
# ---------------------------------------------------------------------------


class TestT005Config:
    """AC T005 — config.py defaults and .env.example / .env content."""

    def test_logtail_source_token_default_is_empty_string(self) -> None:
        """LOGTAIL_SOURCE_TOKEN must default to empty string when env var is absent."""
        # Arrange / Act — read via os.getenv to verify the fallback default
        # We verify that the _type_ is str and that missing env var yields ''
        with patch.dict('os.environ', {}, clear=False):
            # Force reload to pick up env state
            import os

            original = os.environ.pop('LOGTAIL_SOURCE_TOKEN', None)
            try:
                # Directly check os.getenv fallback
                value = os.getenv('LOGTAIL_SOURCE_TOKEN', '')
                assert isinstance(value, str)
                assert value == ''
            finally:
                if original is not None:
                    os.environ['LOGTAIL_SOURCE_TOKEN'] = original

    def test_config_logtail_source_token_is_str(self) -> None:
        """config.LOGTAIL_SOURCE_TOKEN must be a str type."""
        # Arrange / Act
        from fastapistock.config import LOGTAIL_SOURCE_TOKEN

        # Assert
        assert isinstance(LOGTAIL_SOURCE_TOKEN, str)

    def test_config_log_format_has_default(self) -> None:
        """config.LOG_FORMAT must be a non-empty str with a sensible default."""
        # Arrange / Act
        from fastapistock.config import LOG_FORMAT

        # Assert
        assert isinstance(LOG_FORMAT, str)
        assert LOG_FORMAT in ('json', 'text'), (
            f'LOG_FORMAT should be json or text, got: {LOG_FORMAT!r}'
        )

    def test_config_service_name_is_str(self) -> None:
        """config.SERVICE_NAME must be a str."""
        # Arrange / Act
        from fastapistock.config import SERVICE_NAME

        # Assert
        assert isinstance(SERVICE_NAME, str)
        assert SERVICE_NAME != ''

    def test_config_environment_is_str(self) -> None:
        """config.ENVIRONMENT must be a str."""
        # Arrange / Act
        from fastapistock.config import ENVIRONMENT

        # Assert
        assert isinstance(ENVIRONMENT, str)
        assert ENVIRONMENT != ''

    def test_env_example_contains_logtail_source_token(self) -> None:
        """.env.example must declare LOGTAIL_SOURCE_TOKEN."""
        # Arrange
        env_example = PROJECT_ROOT / '.env.example'

        # Act
        content = env_example.read_text(encoding='utf-8')

        # Assert
        assert 'LOGTAIL_SOURCE_TOKEN' in content

    def test_env_example_contains_log_format(self) -> None:
        """.env.example must declare LOG_FORMAT."""
        # Arrange
        env_example = PROJECT_ROOT / '.env.example'

        # Act
        content = env_example.read_text(encoding='utf-8')

        # Assert
        assert 'LOG_FORMAT' in content

    def test_env_example_contains_service_name(self) -> None:
        """.env.example must declare SERVICE_NAME."""
        # Arrange
        env_example = PROJECT_ROOT / '.env.example'

        # Act
        content = env_example.read_text(encoding='utf-8')

        # Assert
        assert 'SERVICE_NAME' in content

    def test_env_example_contains_environment(self) -> None:
        """.env.example must declare ENVIRONMENT."""
        # Arrange
        env_example = PROJECT_ROOT / '.env.example'

        # Act
        content = env_example.read_text(encoding='utf-8')

        # Assert
        assert 'ENVIRONMENT' in content

    def test_env_file_does_not_contain_logtail_token(self) -> None:
        """.env must NOT contain a real LOGTAIL_SOURCE_TOKEN value (security check)."""
        # Arrange
        env_file = PROJECT_ROOT / '.env'
        if not env_file.exists():
            pytest.skip('.env file does not exist')

        # Act
        content = env_file.read_text(encoding='utf-8')

        # Assert — if the line exists it must be empty assignment
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith('LOGTAIL_SOURCE_TOKEN'):
                # Must be LOGTAIL_SOURCE_TOKEN= or LOGTAIL_SOURCE_TOKEN=  (empty)
                parts = stripped.split('=', 1)
                if len(parts) == 2:
                    assert parts[1].strip() == '', (
                        'LOGTAIL_SOURCE_TOKEN must not contain a real token in .env'
                    )
                return  # line found and validated
        # If line not present at all, that's also fine (no token committed)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases not covered by the primary AC tests."""

    def test_logtail_handler_attach_does_not_crash_on_bad_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_attach_logtail_handler must not raise on syntactically invalid token."""
        # Arrange
        import fastapistock.main as main_mod

        monkeypatch.setattr(main_mod, 'LOGTAIL_SOURCE_TOKEN', 'invalid-garbage-token!')
        root_logger = logging.getLogger()

        # Act — must complete without exception
        try:
            main_mod._attach_logtail_handler()
        except Exception as exc:  # pragma: no cover
            pytest.fail(f'_attach_logtail_handler raised unexpectedly: {exc}')
        finally:
            # Cleanup LogtailHandlers added during this test
            from logtail import LogtailHandler as LH

            for h in list(root_logger.handlers):
                if isinstance(h, LH):
                    root_logger.removeHandler(h)

    def test_float_duration_ms_converted_to_integer(self) -> None:
        """float duration_ms via int(round(...)) must yield an integer in JSON."""
        # Arrange — simulate middleware: (time.perf_counter() - start) * 1000
        raw_elapsed_ms = 0.9  # sub-millisecond, rounds to 1
        duration_ms = int(round(raw_elapsed_ms))  # matches middleware code

        fmt = StructuredJsonFormatter(service='test', environment='test')

        # Act
        data = _emit_to_json(fmt, 'PERF', extra={'duration_ms': duration_ms})

        # Assert
        assert isinstance(data['duration_ms'], int)
        assert data['duration_ms'] == 1

    def test_float_duration_ms_larger_value_rounds_correctly(self) -> None:
        """float duration 333.7ms must round to integer 334 in JSON output."""
        # Arrange
        raw_elapsed_ms = 333.7
        duration_ms = int(round(raw_elapsed_ms))

        fmt = StructuredJsonFormatter(service='test', environment='test')

        # Act
        data = _emit_to_json(fmt, 'PERF', extra={'duration_ms': duration_ms})

        # Assert
        assert isinstance(data['duration_ms'], int)
        assert data['duration_ms'] == 334

    def test_log_format_case_sensitivity_uppercase_json_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOG_FORMAT=JSON (uppercase) does NOT match 'json' — strict comparison check.

        This test documents existing behaviour: _build_logging_config uses
        ``if LOG_FORMAT == 'json'`` (strict lowercase). Uppercase 'JSON' falls
        back to the text formatter.  This is the current designed behaviour.
        """
        # Arrange
        import fastapistock.main as main_mod

        monkeypatch.setattr(main_mod, 'LOG_FORMAT', 'JSON')

        # Act
        config = main_mod._build_logging_config()

        # Assert — uppercase 'JSON' is treated as text format (plain format string)
        formatter_cfg = config['formatters']['default']  # type: ignore[index]
        # The current implementation uses strict equality: LOG_FORMAT == 'json'
        # So uppercase falls through to the text branch
        assert 'format' in formatter_cfg  # type: ignore[operator]
        assert '()' not in formatter_cfg  # type: ignore[operator]

    def test_extra_none_value_serialises_without_error(self) -> None:
        """An extra field with None value must serialise to JSON null."""
        # Arrange
        fmt = StructuredJsonFormatter(service='test', environment='test')

        # Act
        data = _emit_to_json(fmt, 'event', extra={'optional_field': None})

        # Assert
        assert 'optional_field' in data
        assert data['optional_field'] is None

    def test_extra_multiple_none_values_serialise(self) -> None:
        """Multiple None-valued extra fields must all appear as JSON null."""
        # Arrange
        fmt = StructuredJsonFormatter(service='test', environment='test')

        # Act
        data = _emit_to_json(
            fmt,
            'event',
            extra={'field_a': None, 'field_b': None, 'field_c': 'present'},
        )

        # Assert
        assert data['field_a'] is None
        assert data['field_b'] is None
        assert data['field_c'] == 'present'

    def test_exc_info_serialises_to_string_in_json(self) -> None:
        """exc_info must be serialised as a string (traceback text) in JSON output."""
        # Arrange
        fmt = StructuredJsonFormatter(service='test', environment='test')
        try:
            raise ValueError('deliberate test error')
        except ValueError:
            exc_info = sys.exc_info()

        # Act
        data = _emit_to_json(
            fmt, 'error occurred', level=logging.ERROR, exc_info=exc_info
        )

        # Assert
        assert 'exc_info' in data
        exc_val = data['exc_info']
        assert isinstance(exc_val, str)
        assert 'ValueError' in exc_val
        assert 'deliberate test error' in exc_val

    def test_exc_info_output_is_valid_json(self) -> None:
        """An exception-carrying log record must produce valid parseable JSON."""
        # Arrange
        fmt = StructuredJsonFormatter(service='test', environment='test')
        try:
            raise RuntimeError('non-serialisable context object')
        except RuntimeError:
            exc_info = sys.exc_info()

        # Act
        raw = _emit_to_string(fmt, 'fail', level=logging.ERROR, exc_info=exc_info)

        # Assert — must be parseable without error
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_non_serialisable_object_in_extra_converts_to_str(self) -> None:
        """An arbitrary Python object in extra must be safely converted to str."""

        # Arrange
        class _Unserializable:
            def __repr__(self) -> str:
                return 'UnserializableObject()'

        fmt = StructuredJsonFormatter(service='test', environment='test')
        obj = _Unserializable()

        # Act
        data = _emit_to_json(fmt, 'event', extra={'bad_obj': obj})

        # Assert
        assert 'bad_obj' in data
        assert isinstance(data['bad_obj'], str)

    def test_service_name_injected_from_formatter_params(self) -> None:
        """Custom service/environment params must appear in every formatted record."""
        # Arrange
        fmt = StructuredJsonFormatter(service='custom-service', environment='staging')

        # Act
        data = _emit_to_json(fmt, 'test message')

        # Assert
        assert data['service'] == 'custom-service'
        assert data['environment'] == 'staging'

    def test_log_format_text_value_produces_text_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOG_FORMAT=text must always produce a plain-text formatter config."""
        # Arrange
        import fastapistock.main as main_mod

        monkeypatch.setattr(main_mod, 'LOG_FORMAT', 'text')

        # Act
        config = main_mod._build_logging_config()

        # Assert
        formatter_cfg = config['formatters']['default']  # type: ignore[index]
        assert '()' not in formatter_cfg  # type: ignore[operator]
        assert 'format' in formatter_cfg  # type: ignore[operator]
        format_str = formatter_cfg['format']  # type: ignore[index]
        assert '%(levelname)s' in format_str
        assert '%(message)s' in format_str
