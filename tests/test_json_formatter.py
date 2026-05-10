from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import sys
import uuid

import pytest

from azure_functions_logging._json_formatter import JsonFormatter


def _make_record(level: int = logging.INFO, msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_basic_json_output_is_valid_and_has_expected_fields() -> None:
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "basic message")

    output = formatter.format(record)
    payload = json.loads(output)

    # NDJSON: formatter no longer appends \n; StreamHandler adds it
    assert json.loads(output) is not None
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["message"] == "basic message"
    assert payload["invocation_id"] is None
    assert payload["function_name"] is None
    assert payload["trace_id"] is None
    assert payload["cold_start"] is None
    assert payload["exception"] is None
    assert payload["extra"] == {}


def test_context_fields_included_when_present() -> None:
    formatter = JsonFormatter()
    record = _make_record(msg="with context")
    record.invocation_id = "inv-1"
    record.function_name = "fn-1"
    record.trace_id = "trace-1"

    payload = json.loads(formatter.format(record))

    assert payload["invocation_id"] == "inv-1"
    assert payload["function_name"] == "fn-1"
    assert payload["trace_id"] == "trace-1"


def test_cold_start_field_for_true_false_and_none() -> None:
    formatter = JsonFormatter()

    record_true = _make_record(msg="cold")
    record_true.cold_start = True
    assert json.loads(formatter.format(record_true))["cold_start"] is True

    record_false = _make_record(msg="warm")
    record_false.cold_start = False
    assert json.loads(formatter.format(record_false))["cold_start"] is False

    record_none = _make_record(msg="none")
    record_none.cold_start = None
    assert json.loads(formatter.format(record_none))["cold_start"] is None


def test_exception_info_is_formatted_in_exception_field() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record(logging.ERROR, "failed")
        record.exc_info = sys.exc_info()

    payload = json.loads(formatter.format(record))

    assert payload["exception"] is not None
    assert "Traceback" in payload["exception"]
    assert "ValueError: boom" in payload["exception"]


def test_bound_context_is_collected_in_extra_field() -> None:
    formatter = JsonFormatter()
    record = _make_record(msg="bound")
    record.user_id = "abc"
    record.request_id = "req-1"
    record.invocation_id = "inv-1"

    payload = json.loads(formatter.format(record))

    assert payload["extra"] == {"request_id": "req-1", "user_id": "abc"}


def test_timestamp_is_iso8601_with_timezone() -> None:
    formatter = JsonFormatter()
    record = _make_record(msg="time")
    record.created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc).timestamp()

    payload = json.loads(formatter.format(record))
    parsed = datetime.fromisoformat(payload["timestamp"])

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def test_unserializable_extra_does_not_drop_log_line() -> None:
    """Issue #77: a logging library must never drop logs because of unserializable extra."""
    formatter = JsonFormatter()
    record = _make_record(msg="payload")
    record.when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    record.amount = Decimal("1.23")
    record.request_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

    output = formatter.format(record)
    payload = json.loads(output)

    assert payload["message"] == "payload"
    assert payload["extra"]["when"] == "2026-01-02 03:04:05+00:00"
    assert payload["extra"]["amount"] == "1.23"
    assert payload["extra"]["request_id"] == "12345678-1234-5678-1234-567812345678"


def test_unserializable_extra_with_dataclass_falls_back_to_str() -> None:
    @dataclass
    class Order:
        id: str
        total: int

    formatter = JsonFormatter()
    record = _make_record(msg="order")
    record.order = Order(id="o-1", total=42)

    payload = json.loads(formatter.format(record))

    assert "order" in payload["extra"]
    assert "Order" in payload["extra"]["order"]
    assert "o-1" in payload["extra"]["order"]


def test_unserializable_extra_where_str_raises_returns_sentinel() -> None:
    class Hostile:
        def __str__(self) -> str:
            raise RuntimeError("no")

    formatter = JsonFormatter()
    record = _make_record(msg="hostile")
    record.bad = Hostile()

    payload = json.loads(formatter.format(record))

    assert payload["extra"]["bad"] == "<unserializable:Hostile>"



# ---- Fail-safe tests (#101) ---------------------------------------------


class _HostileStr:
    """Object whose __str__ raises — used to break message rendering."""

    def __str__(self) -> str:  # noqa: D401
        raise RuntimeError("boom in __str__")

    def __repr__(self) -> str:  # noqa: D401
        raise RuntimeError("boom in __repr__")


def test_format_survives_hostile_message_str() -> None:
    formatter = JsonFormatter()
    # Use %-format with a single %s arg whose __str__ raises
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="value=%s",
        args=(_HostileStr(),),
        exc_info=None,
    )

    output = formatter.format(record)
    payload = json.loads(output)  # must be valid JSON
    assert payload["level"] == "INFO"
    assert "<unrenderable message:" in payload["message"]


def test_format_survives_malformed_exc_info() -> None:
    formatter = JsonFormatter()
    record = _make_record(logging.ERROR, "boom")
    # Invalid exc_info triple: missing traceback object causes formatException to fail
    record.exc_info = (RuntimeError, RuntimeError("x"), "not a traceback")  # type: ignore[assignment]

    output = formatter.format(record)
    payload = json.loads(output)
    assert payload["level"] == "ERROR"
    assert payload["exception"] is not None
    assert "<unformattable exception:" in payload["exception"]


def test_format_survives_cyclic_extra_payload() -> None:
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "cyclic")
    cycle: dict[str, object] = {}
    cycle["self"] = cycle  # self-referential — json.dumps would normally raise
    record.cyclic = cycle

    output = formatter.format(record)
    payload = json.loads(output)  # must still be valid JSON
    # Either the default coerced it to a string, or last-resort fallback fired
    assert payload["level"] == "INFO"
    assert "extra" in payload


def test_format_emergency_fallback_when_payload_dict_unserializable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If even the second json.dumps attempt fails, emergency payload is emitted."""
    formatter = JsonFormatter()
    record = _make_record(logging.WARNING, "force emergency")



    call_count = {"n": 0}
    real_dumps = json.dumps

    def always_raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise TypeError("forced failure")
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr("azure_functions_logging._json_formatter.json.dumps", always_raise)

    output = formatter.format(record)
    payload = json.loads(output)  # emergency payload must be valid JSON
    assert payload["message"] == "<emergency fallback: formatter failed>"
    assert payload["extra"] == {"__serialization_error__": True}
    assert payload["level"] == "WARNING"


def test_format_handles_invalid_timestamp() -> None:
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "bad ts")
    record.created = float("nan")  # fromtimestamp will raise

    output = formatter.format(record)
    payload = json.loads(output)
    assert payload["timestamp"] == "1970-01-01T00:00:00+00:00"
