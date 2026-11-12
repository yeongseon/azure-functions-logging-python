"""Opt-in ``profile="otel"`` JSON schema: golden output, defaults unchanged, no secret leaks."""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import pytest

from azure_functions_logging import JsonFormatter, logging_context
from azure_functions_logging._context import ContextFilter
from azure_functions_logging._host_instance import get_host_instance_id
from azure_functions_logging._json_formatter import severity_number
from azure_functions_logging._secure import _SecureRedactionFilter

CANARY = "CANARY_OTEL_PROFILE"
_DEFAULT_KEYS = [
    "timestamp",
    "level",
    "logger",
    "message",
    "invocation_id",
    "function_name",
    "trace_id",
    "span_id",
    "cold_start",
    "host_instance_id",
    "exception",
    "extra",
]


def _record(**attrs: Any) -> logging.LogRecord:
    record = logging.makeLogRecord(
        {"name": "svc", "levelno": logging.WARNING, "levelname": "WARNING", "msg": "hello"}
    )
    record.created = 0.0
    for key, value in attrs.items():
        setattr(record, key, value)
    return record


def _fmt(formatter: logging.Formatter, record: logging.LogRecord) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(formatter.format(record))
    return out


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "inst-1")


def test_default_schema_is_unchanged() -> None:
    record = _record(invocation_id="i-1", function_name="fn", cold_start=True)
    assert list(_fmt(JsonFormatter(), record)) == _DEFAULT_KEYS
    assert list(_fmt(JsonFormatter(profile="default"), record)) == _DEFAULT_KEYS


def test_invalid_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="profile"):
        JsonFormatter(profile="nope")  # type: ignore[arg-type]


def test_otel_profile_golden_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_SITE_NAME", "myapp")
    record = _record(
        invocation_id="i-1",
        function_name="fn",
        trace_id="a" * 32,
        span_id="b" * 16,
        cold_start=False,
        host_instance_id="host-9",
        order_id=7,
    )
    assert _fmt(JsonFormatter(profile="otel"), record) == {
        "timestamp": "1970-01-01T00:00:00+00:00",
        "level": "WARNING",
        "severity_number": 13,
        "logger": "svc",
        "message": "hello",
        "faas.invocation.id": "i-1",
        "faas.name": "myapp/fn",
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "faas.coldstart": False,
        "faas.instance": "host-9",
        "extra": {"order_id": 7},
    }


def test_otel_profile_omits_absent_context_and_keeps_false_values() -> None:
    record = _record(cold_start=False, host_instance_id=None)
    payload = _fmt(JsonFormatter(profile="otel"), record)
    assert payload["faas.coldstart"] is False
    for key in ("faas.invocation.id", "faas.name", "trace_id", "span_id", "exception"):
        assert key not in payload
    expected_instance = get_host_instance_id()
    if expected_instance is None:
        assert "faas.instance" not in payload
    else:
        assert payload["faas.instance"] == expected_instance
    assert "invocation_id" not in payload and "cold_start" not in payload


def test_faas_name_without_site_is_the_bare_function_name() -> None:
    payload = _fmt(JsonFormatter(profile="otel"), _record(function_name="fn"))
    assert payload["faas.name"] == "fn"


def test_exception_fields_are_hoisted_from_exc_info() -> None:
    try:
        raise ValueError("bad value")
    except ValueError:
        import sys

        record = _record(exc_info=sys.exc_info())
    payload = _fmt(JsonFormatter(profile="otel"), record)
    assert payload["exception.type"] == "ValueError"
    assert payload["exception.message"] == "bad value"
    assert "Traceback" in payload["exception.stacktrace"]
    assert payload["exception"] == payload["exception.stacktrace"]
    assert not any(k.startswith("exception.") for k in payload["extra"])


def test_default_profile_keeps_exception_attrs_inside_extra() -> None:
    record = _record(**{"exception.type": "X", "exception.message": "m"})
    payload = _fmt(JsonFormatter(), record)
    assert payload["extra"]["exception.type"] == "X"
    assert "exception.type" not in payload


def test_secure_redaction_canary_never_reaches_otel_profile_output() -> None:
    try:
        raise RuntimeError(f"password={CANARY}")
    except RuntimeError:
        import sys

        record = _record(exc_info=sys.exc_info(), msg=f"token={CANARY}")
    _SecureRedactionFilter().filter(record)
    text = JsonFormatter(profile="otel").format(record)
    assert CANARY not in text
    payload = json.loads(text)
    assert payload["exception.type"] == "RuntimeError"
    assert "***" in payload["exception.message"]


def test_formatting_does_not_mutate_the_shared_record_across_sinks() -> None:
    record = _record(invocation_id="i-1", function_name="fn", order_id=1)
    before = dict(record.__dict__)
    default_out = JsonFormatter().format(record)
    otel_out = JsonFormatter(profile="otel").format(record)
    assert record.__dict__ == before
    assert JsonFormatter().format(record) == default_out
    assert json.loads(otel_out)["faas.invocation.id"] == "i-1"


def test_mixed_default_and_otel_handlers_on_one_logger_keep_correlation() -> None:
    default_stream, otel_stream = io.StringIO(), io.StringIO()
    handlers: list[logging.Handler] = []
    for stream, profile in ((default_stream, "default"), (otel_stream, "otel")):
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter(profile=profile))  # type: ignore[arg-type]
        handler.addFilter(ContextFilter())
        handler.addFilter(_SecureRedactionFilter())
        handlers.append(handler)
    logger = logging.getLogger("otel.mixed")
    logger.handlers = handlers
    logger.propagate = False

    class Ctx:
        invocation_id = "inv-mixed"
        function_name = "mixed_fn"
        trace_context = None

    try:
        with logging_context(Ctx()):
            logger.warning("password=%s", CANARY)
    finally:
        logger.handlers = []
    default_payload = json.loads(default_stream.getvalue())
    otel_payload = json.loads(otel_stream.getvalue())
    assert default_payload["invocation_id"] == "inv-mixed"
    assert otel_payload["faas.invocation.id"] == "inv-mixed"
    assert CANARY not in default_stream.getvalue() + otel_stream.getvalue()


@pytest.mark.parametrize(
    ("levelno", "expected"),
    [
        (0, 0),
        (9, 0),
        (10, 5),
        (11, 6),
        (13, 8),
        (19, 8),
        (20, 9),
        (25, 12),
        (30, 13),
        (40, 17),
        (50, 21),
        (51, 22),
        (53, 24),
        (54, 24),
        (1000, 24),
    ],
)
def test_severity_number_table(levelno: int, expected: int) -> None:
    assert severity_number(levelno) == expected


def test_severity_number_matches_the_otel_sdk_when_installed() -> None:
    internal = pytest.importorskip("opentelemetry.sdk._logs._internal")
    for levelno in range(0, 120):
        assert severity_number(levelno) == int(internal.std_to_otel(levelno).value), levelno


def test_profile_needs_no_opentelemetry_import(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    import sys

    real_import = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    for mod in [m for m in sys.modules if m.startswith("opentelemetry")]:
        monkeypatch.delitem(sys.modules, mod)
    monkeypatch.setattr(builtins, "__import__", guarded)
    payload = _fmt(JsonFormatter(profile="otel"), _record(invocation_id="i"))
    assert payload["faas.invocation.id"] == "i"
