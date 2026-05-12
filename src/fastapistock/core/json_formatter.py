"""Custom JSON log formatter for structured logging (Spec 007).

Extends ``pythonjsonlogger.json.JsonFormatter`` to:
- Inject fixed ``service`` and ``environment`` fields from config.
- Flatten ``extra`` dict fields directly into the top-level JSON record.
- Serialise non-JSON-native types (``Decimal``, ``datetime``) via ``str()``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from pythonjsonlogger.json import JsonFormatter


def _safe_value(value: object) -> object:
    """Convert a log field value to a JSON-serialisable form.

    Args:
        value: Arbitrary Python object from a log record's extra dict.

    Returns:
        The original value if already JSON-serialisable, otherwise ``str(value)``.
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (Decimal, datetime)):
        return str(value)
    return str(value)


# Fields that are internal to LogRecord and should not be forwarded as
# top-level JSON keys even if they technically live on the record.
_RESERVED_ATTRS: frozenset[str] = frozenset(
    {
        'args',
        'created',
        'exc_info',
        'exc_text',
        'filename',
        'funcName',
        'levelname',
        'levelno',
        'lineno',
        'message',
        'module',
        'msecs',
        'msg',
        'name',
        'pathname',
        'process',
        'processName',
        'relativeCreated',
        'stack_info',
        'taskName',
        'thread',
        'threadName',
    }
)


class StructuredJsonFormatter(JsonFormatter):  # type: ignore[misc]
    """JSON formatter that expands ``extra`` fields and injects context.

    Note: ``# type: ignore[misc]`` suppresses the mypy "Class cannot subclass
    JsonFormatter (has type Any)" error caused by missing stubs for the
    ``python-json-logger`` package.

    Args:
        service: Value for the ``service`` JSON field (from ``SERVICE_NAME`` env).
        environment: Value for the ``environment`` JSON field.
        json_default: Optional JSON default encoder passed to parent.
        json_encoder: Optional JSON encoder class passed to parent.
        json_indent: Indent level for pretty-printing (``None`` = compact).
        json_ensure_ascii: Whether to escape non-ASCII chars in JSON output.
    """

    def __init__(
        self,
        service: str,
        environment: str,
        json_default: Callable[..., object] | None = None,
        json_encoder: Callable[..., object] | None = None,
        json_indent: int | str | None = None,
        json_ensure_ascii: bool = True,
    ) -> None:
        super().__init__(
            json_default=json_default,
            json_encoder=json_encoder,
            json_indent=json_indent,
            json_ensure_ascii=json_ensure_ascii,
        )
        self._service = service
        self._environment = environment

    def add_fields(
        self,
        log_record: dict[str, object],
        record: logging.LogRecord,
        message_dict: dict[str, object],
    ) -> None:
        """Populate ``log_record`` with base fields plus extra dict contents.

        Args:
            log_record: Mutable output dict being built for JSON serialisation.
            record: The original :class:`logging.LogRecord`.
            message_dict: Pre-parsed fields from the formatter (exc_info etc.).
        """
        super().add_fields(log_record, record, message_dict)

        # Inject fixed context fields.
        log_record['service'] = self._service
        log_record['environment'] = self._environment

        # Expand every non-reserved attribute that was injected via extra={}.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and key not in log_record:
                log_record[key] = _safe_value(value)

    def jsonify_log_record(self, log_record: dict[str, object]) -> str:
        """Serialise ``log_record`` to a JSON string with safe fallbacks.

        Overrides the parent to intercept non-serialisable values that slipped
        through ``add_fields`` (e.g. objects nested inside list values).

        Args:
            log_record: Fully populated record dict.

        Returns:
            Single-line JSON string.
        """
        safe_record = {k: _safe_value(v) for k, v in log_record.items()}
        # super() returns Any (no stubs); cast to str is safe — the library
        # always returns a string from jsonify_log_record.
        result: str = super().jsonify_log_record(safe_record)  # type: ignore[assignment]
        return result
