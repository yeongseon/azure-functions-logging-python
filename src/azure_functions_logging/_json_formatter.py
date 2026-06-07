"""JSON log formatter for azure-functions-logging."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from ._logger import _LIBRARY_RESERVED_KEYS, _STDLIB_RECORD_KEYS

_STANDARD_RECORD_FIELDS: frozenset[str] = _STDLIB_RECORD_KEYS
_CONTEXT_FIELDS: frozenset[str] = _LIBRARY_RESERVED_KEYS


# Maximum length (in characters) of the string produced by the ``json.dumps``
# ``default=`` fallback path. A single very large object (e.g. a SQLAlchemy
# result row, a deeply nested config, a full HTTP body) can otherwise bloat
# every log record it appears in and risk hitting Application Insights
# per-record size limits. Natively serializable values (strings, numbers,
# booleans, lists, dicts) are NOT affected by this limit.
_MAX_SERIALIZED_EXTRA_LENGTH = 2048
_TRUNCATION_SUFFIX = "...<truncated>"

# Maximum recursion depth when walking the ``extra`` payload to coerce it into
# a JSON-safe structure. Beyond this depth, the offending value is replaced
# with a sentinel so a pathological nested object (e.g. accidentally logging a
# whole ORM graph) cannot blow the stack inside ``format()``.
_MAX_RECURSION_DEPTH = 32


def _json_default(value: Any) -> str:
    """Fallback serializer for ``json.dumps``.

    A logging library must never lose log records because of an unserializable
    ``extra`` value (datetime, Decimal, UUID, dataclass, exception, request
    objects, etc.). This callable coerces unknown values to ``str(value)`` and
    returns a sentinel string if even ``str()`` raises, so the formatter always
    produces a valid JSON document.

    Strings longer than :data:`_MAX_SERIALIZED_EXTRA_LENGTH` are truncated and
    suffixed with :data:`_TRUNCATION_SUFFIX` to bound per-record growth.
    """
    try:
        text = str(value)
    except Exception:
        return f"<unserializable:{type(value).__name__}>"
    if len(text) > _MAX_SERIALIZED_EXTRA_LENGTH:
        return text[:_MAX_SERIALIZED_EXTRA_LENGTH] + _TRUNCATION_SUFFIX
    return text


def _safe_key(key: Any) -> str:
    """Coerce a dict key to ``str`` without ever raising."""
    if isinstance(key, str):
        return key
    try:
        return str(key)
    except Exception:
        return f"<unserializable-key:{type(key).__name__}>"


def _to_json_safe(
    value: Any,
    _seen: frozenset[int] | None = None,
    _depth: int = 0,
) -> Any:
    """Return a JSON-safe copy of ``value``.

    Coerces non-string dict keys via :func:`_safe_key`, recurses through
    dicts/lists/tuples/sets, converts sets to lists, detects reference cycles,
    and bounds recursion depth. Primitive values pass through unchanged;
    anything else is left for the ``json.dumps`` ``default=`` path.
    """
    if _depth > _MAX_RECURSION_DEPTH:
        return f"<max-depth:{_MAX_RECURSION_DEPTH}>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        seen = _seen if _seen is not None else frozenset()
        if id(value) in seen:
            return "<cyclic>"
        seen = seen | {id(value)}
        if isinstance(value, dict):
            return {
                _safe_key(k): _to_json_safe(v, seen, _depth + 1)
                for k, v in value.items()
            }
        return [_to_json_safe(item, seen, _depth + 1) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter.

    Output is newline-delimited JSON (NDJSON), with one JSON object per log line.
    Context fields (invocation_id, function_name, etc.) are included when present
    on the LogRecord (set by ContextFilter).

    Unserializable values in ``extra`` are coerced to strings via
    :func:`_json_default` rather than dropping the log record.
    """

    def __init__(self) -> None:
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as one NDJSON object.

        Fully fail-safe: every step (message rendering, exception formatting,
        timestamp, JSON serialization) is wrapped so that a hostile
        ``__str__`` / ``__repr__``, a malformed ``exc_info`` triple, or a
        cyclic ``extra`` payload never raises out of ``format()``. Worst-case
        we still emit a single valid JSON object with sentinel values.
        """
        message = _safe_get_message(record)
        timestamp = _safe_timestamp(record)

        exception: str | None = None
        if record.exc_info:
            exception = _safe_format_exception(self, record.exc_info)

        excluded_fields = _STANDARD_RECORD_FIELDS | _CONTEXT_FIELDS
        extra = {key: value for key, value in record.__dict__.items() if key not in excluded_fields}
        extra = _to_json_safe(extra)

        payload = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "invocation_id": getattr(record, "invocation_id", None),
            "function_name": getattr(record, "function_name", None),
            "trace_id": getattr(record, "trace_id", None),
            "cold_start": getattr(record, "cold_start", None),
            "exception": exception,
            "extra": extra,
        }

        try:
            return json.dumps(payload, ensure_ascii=False, default=_json_default)
        except Exception:
            # Last-resort fallback: drop ``extra`` (the most likely culprit
            # for cyclic / unserializable payloads) and re-attempt. If even
            # that fails, emit a minimal hand-built JSON object so the
            # logging pipeline never breaks.
            payload["extra"] = {"__serialization_error__": True}
            try:
                return json.dumps(payload, ensure_ascii=False, default=_json_default)
            except Exception:
                return _emergency_payload(record)


def _safe_get_message(record: logging.LogRecord) -> str:
    """Render ``record.getMessage()`` without ever raising."""
    try:
        return record.getMessage()
    except Exception as exc:
        return f"<unrenderable message: {type(exc).__name__}>"


def _safe_timestamp(record: logging.LogRecord) -> str:
    """Format the record timestamp without ever raising."""
    try:
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
    except Exception:
        return "1970-01-01T00:00:00+00:00"


def _safe_format_exception(formatter: logging.Formatter, exc_info: Any) -> str:
    """Format ``exc_info`` without ever raising."""
    try:
        return formatter.formatException(exc_info)
    except Exception as exc:
        return f"<unformattable exception: {type(exc).__name__}>"


def _emergency_payload(record: logging.LogRecord) -> str:
    """Build a minimal valid JSON line when every other path failed."""
    level = getattr(record, "levelname", "UNKNOWN")
    name = getattr(record, "name", "unknown")
    return json.dumps(
        {
            "timestamp": "1970-01-01T00:00:00+00:00",
            "level": str(level),
            "logger": str(name),
            "message": "<emergency fallback: formatter failed>",
            "invocation_id": None,
            "function_name": None,
            "trace_id": None,
            "cold_start": None,
            "exception": None,
            "extra": {"__serialization_error__": True},
        },
        ensure_ascii=False,
    )
