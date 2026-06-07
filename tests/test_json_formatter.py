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


# ---- Fallback truncation (#82) ------------------------------------------


def test_fallback_value_at_max_length_is_not_truncated() -> None:
    """#82 boundary: str(value) at exactly _MAX_SERIALIZED_EXTRA_LENGTH passes through."""
    from azure_functions_logging._json_formatter import _MAX_SERIALIZED_EXTRA_LENGTH

    class Boundary:
        def __str__(self) -> str:
            return "x" * _MAX_SERIALIZED_EXTRA_LENGTH

    formatter = JsonFormatter()
    record = _make_record(msg="boundary")
    record.payload = Boundary()

    output = formatter.format(record)
    payload = json.loads(output)

    assert payload["extra"]["payload"] == "x" * _MAX_SERIALIZED_EXTRA_LENGTH
    assert "<truncated>" not in payload["extra"]["payload"]


def test_fallback_value_over_max_length_is_truncated_with_suffix() -> None:
    """Issue #82: str(value) longer than the limit is truncated and suffixed."""
    from azure_functions_logging._json_formatter import (
        _MAX_SERIALIZED_EXTRA_LENGTH,
        _TRUNCATION_SUFFIX,
    )

    class Huge:
        def __str__(self) -> str:
            return "a" * (_MAX_SERIALIZED_EXTRA_LENGTH + 500)

    formatter = JsonFormatter()
    record = _make_record(msg="huge")
    record.payload = Huge()

    output = formatter.format(record)
    # Output must remain a valid JSON document.
    payload = json.loads(output)

    rendered = payload["extra"]["payload"]
    assert rendered.endswith(_TRUNCATION_SUFFIX)
    assert len(rendered) == _MAX_SERIALIZED_EXTRA_LENGTH + len(_TRUNCATION_SUFFIX)
    # The first _MAX_SERIALIZED_EXTRA_LENGTH chars are the original prefix.
    assert rendered[:_MAX_SERIALIZED_EXTRA_LENGTH] == "a" * _MAX_SERIALIZED_EXTRA_LENGTH


def test_truncation_does_not_apply_to_native_serializable_values() -> None:
    """Issue #82 scope: the limit only applies to the json.dumps default= path.

    Plain strings/ints/lists/dicts are serialized natively by json and must
    pass through untouched even if they exceed the limit.
    """
    from azure_functions_logging._json_formatter import _MAX_SERIALIZED_EXTRA_LENGTH

    big_string = "z" * (_MAX_SERIALIZED_EXTRA_LENGTH + 100)
    formatter = JsonFormatter()
    record = _make_record(msg="native")
    record.payload = big_string

    payload = json.loads(formatter.format(record))

    # Native string must not be touched by the fallback truncation.
    assert payload["extra"]["payload"] == big_string
    assert "<truncated>" not in payload["extra"]["payload"]


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


def test_format_coerces_non_string_dict_keys() -> None:
    """Non-string dict keys in extra are coerced via _safe_key."""
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "non-string keys")
    record.payload = {1: "one", (2, 3): "tuple-key", None: "none-key"}

    output = formatter.format(record)
    payload = json.loads(output)
    assert payload["extra"]["payload"] == {
        "1": "one",
        "(2, 3)": "tuple-key",
        "None": "none-key",
    }


def test_format_handles_nested_cyclic_extra_payload() -> None:
    """Cycles nested inside lists/dicts are replaced with a sentinel."""
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "nested cycle")
    inner: dict[str, object] = {"name": "inner"}
    outer: dict[str, object] = {"items": [inner, {"deep": inner}]}
    inner["back"] = outer  # creates a cycle through nested containers
    record.tree = outer

    output = formatter.format(record)
    payload = json.loads(output)  # must be valid JSON
    assert payload["level"] == "INFO"
    assert "tree" in payload["extra"]
    serialized = json.dumps(payload["extra"]["tree"])
    assert "<cyclic>" in serialized


def test_format_converts_sets_to_lists_in_extra() -> None:
    """Sets are not JSON-native; safe conversion turns them into lists."""
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "set extra")
    record.tags = {"a", "b", "c"}

    output = formatter.format(record)
    payload = json.loads(output)
    assert isinstance(payload["extra"]["tags"], list)
    assert sorted(payload["extra"]["tags"]) == ["a", "b", "c"]


def test_format_truncates_extra_at_max_recursion_depth() -> None:
    """Pathologically deep nesting is replaced with a depth sentinel."""
    from azure_functions_logging._json_formatter import _MAX_RECURSION_DEPTH

    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "deep nesting")
    deep: dict[str, object] = {"v": "leaf"}
    for _ in range(_MAX_RECURSION_DEPTH + 5):
        deep = {"n": deep}
    record.deep = deep

    output = formatter.format(record)
    payload = json.loads(output)
    assert f"<max-depth:{_MAX_RECURSION_DEPTH}>" in json.dumps(payload["extra"]["deep"])


def test_format_does_not_misclassify_dag_as_cycle() -> None:
    """A shared (non-cyclic) child appearing in two sibling positions must be
    expanded twice, not replaced with the cyclic sentinel."""
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "dag")
    shared = {"name": "shared"}
    record.payload = {"a": shared, "b": shared}

    output = formatter.format(record)
    payload = json.loads(output)
    assert payload["extra"]["payload"] == {
        "a": {"name": "shared"},
        "b": {"name": "shared"},
    }


# ---------------------------------------------------------------------------
# JsonFormatter — native string truncation (issue #165)
# ---------------------------------------------------------------------------


def test_truncate_native_strings_disabled_by_default() -> None:
    """Default formatter leaves long native strings intact."""
    formatter = JsonFormatter()
    record = _make_record(logging.INFO, "msg")
    record.long_field = "x" * 5000

    payload = json.loads(formatter.format(record))
    assert payload["extra"]["long_field"] == "x" * 5000


def test_truncate_native_strings_enabled() -> None:
    """truncate_native_strings=True clips strings at max_string_length."""
    formatter = JsonFormatter(truncate_native_strings=True, max_string_length=10)
    record = _make_record(logging.INFO, "msg")
    record.long_field = "abcdefghij" + "extra"

    payload = json.loads(formatter.format(record))
    assert payload["extra"]["long_field"] == "abcdefghij…"


def test_truncate_native_strings_exact_length_not_truncated() -> None:
    """Strings at exactly max_string_length are not truncated."""
    formatter = JsonFormatter(truncate_native_strings=True, max_string_length=5)
    record = _make_record(logging.INFO, "msg")
    record.exact = "hello"

    payload = json.loads(formatter.format(record))
    assert payload["extra"]["exact"] == "hello"


def test_truncate_native_strings_nested_dict() -> None:
    """Truncation recurses into nested dicts."""
    formatter = JsonFormatter(truncate_native_strings=True, max_string_length=3)
    record = _make_record(logging.INFO, "msg")
    record.data = {"inner": "toolong", "num": 42}

    payload = json.loads(formatter.format(record))
    assert payload["extra"]["data"]["inner"] == "too…"
    assert payload["extra"]["data"]["num"] == 42


def test_truncate_native_strings_nested_list() -> None:
    """Truncation recurses into lists."""
    formatter = JsonFormatter(truncate_native_strings=True, max_string_length=4)
    record = _make_record(logging.INFO, "msg")
    record.items = ["short", "ab", "toolongstring"]

    payload = json.loads(formatter.format(record))
    assert payload["extra"]["items"] == ["shor…", "ab", "tool…"]


def test_truncate_native_strings_custom_max_length() -> None:
    """max_string_length is respected."""
    formatter = JsonFormatter(truncate_native_strings=True, max_string_length=2048)
    record = _make_record(logging.INFO, "msg")
    record.exact = "x" * 2048
    record.over = "x" * 2049

    payload = json.loads(formatter.format(record))
    assert payload["extra"]["exact"] == "x" * 2048
    assert payload["extra"]["over"] == "x" * 2048 + "…"


def test_truncate_native_strings_does_not_affect_fallback_truncation() -> None:
    """Existing fallback truncation (_json_default path) is unaffected."""
    formatter = JsonFormatter(truncate_native_strings=False)
    record = _make_record(logging.INFO, "msg")

    class _Big:
        def __str__(self) -> str:
            return "z" * 3000

    record.obj = _Big()

    payload = json.loads(formatter.format(record))
    # fallback truncation always applies
    assert payload["extra"]["obj"].endswith("...<truncated>")


def test_truncate_native_strings_negative_max_raises() -> None:
    """max_string_length < 0 raises ValueError."""
    with pytest.raises(ValueError, match="max_string_length"):
        JsonFormatter(truncate_native_strings=True, max_string_length=-1)


def test_truncate_native_strings_zero_max_clips_all_non_empty() -> None:
    """max_string_length=0 clips any non-empty string to the ellipsis suffix only."""
    formatter = JsonFormatter(truncate_native_strings=True, max_string_length=0)
    record = _make_record(logging.INFO, "msg")
    record.nonempty = "hello"
    record.empty = ""

    payload = json.loads(formatter.format(record))
    assert payload["extra"]["nonempty"] == "…"
    assert payload["extra"]["empty"] == ""  # empty string ≤ 0 chars — not truncated


def test_truncate_native_strings_with_non_serializable_in_extra() -> None:
    """Non-serializable objects are coerced by _json_default; their coerced string
    is not further truncated by _truncate_native_strings because _json_default fires
    during json.dumps which runs AFTER _truncate_native_strings.
    """
    formatter = JsonFormatter(truncate_native_strings=True, max_string_length=5)
    record = _make_record(logging.INFO, "msg")

    class _Short:
        def __str__(self) -> str:
            return "abc"  # well within max

    class _Long:
        def __str__(self) -> str:
            return "x" * 3000  # beyond max — BUT truncated by _json_default, not native

    record.short_obj = _Short()
    record.long_obj = _Long()

    payload = json.loads(formatter.format(record))
    # _Short coerced to 'abc' by _json_default (within _MAX_SERIALIZED_EXTRA_LENGTH)
    assert payload["extra"]["short_obj"] == "abc"
    # _Long coerced by _json_default and truncated to _MAX_SERIALIZED_EXTRA_LENGTH (2048)
    assert payload["extra"]["long_obj"].endswith("...<truncated>")
