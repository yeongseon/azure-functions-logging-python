"""Tests for SamplingFilter and RedactionFilter."""

from __future__ import annotations

import logging
import time

import pytest

from azure_functions_logging._filters import RedactionFilter, SamplingFilter


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


# ---------------------------------------------------------------------------
# SamplingFilter tests
# ---------------------------------------------------------------------------


def test_sampling_filter_passes_records_within_rate() -> None:
    flt = SamplingFilter(rate=3, window=10.0)
    for _ in range(3):
        assert flt.filter(_make_record()) is True


def test_sampling_filter_drops_records_beyond_rate() -> None:
    flt = SamplingFilter(rate=2, window=10.0)
    assert flt.filter(_make_record()) is True
    assert flt.filter(_make_record()) is True
    assert flt.filter(_make_record()) is False


def test_sampling_filter_resets_after_window() -> None:
    flt = SamplingFilter(rate=1, window=0.05)
    assert flt.filter(_make_record()) is True
    assert flt.filter(_make_record()) is False  # exceeded within window
    time.sleep(0.06)
    assert flt.filter(_make_record()) is True  # window reset


def test_sampling_filter_always_passes_warning_and_above() -> None:
    flt = SamplingFilter(rate=1, window=10.0)
    # Exhaust the rate
    flt.filter(_make_record())
    flt.filter(_make_record())

    assert flt.filter(_make_record(logging.WARNING)) is True
    assert flt.filter(_make_record(logging.ERROR)) is True
    assert flt.filter(_make_record(logging.CRITICAL)) is True


def test_sampling_filter_invalid_rate_raises() -> None:
    with pytest.raises(ValueError, match="rate"):
        SamplingFilter(rate=0)


def test_sampling_filter_invalid_window_raises() -> None:
    with pytest.raises(ValueError, match="window"):
        SamplingFilter(rate=1, window=0.0)


# ---------------------------------------------------------------------------
# RedactionFilter tests
# ---------------------------------------------------------------------------


def test_redaction_filter_masks_default_sensitive_keys() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="login")
    setattr(record, "password", "s3cr3t")
    setattr(record, "token", "tok123")

    result = flt.filter(record)

    assert result is True
    assert getattr(record, "password") == "***"
    assert getattr(record, "token") == "***"


def test_redaction_filter_leaves_non_sensitive_keys_unchanged() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="safe")
    setattr(record, "user_id", "u-1")
    setattr(record, "request_id", "r-1")

    flt.filter(record)

    assert getattr(record, "user_id") == "u-1"
    assert getattr(record, "request_id") == "r-1"


def test_redaction_filter_custom_sensitive_keys() -> None:
    flt = RedactionFilter(sensitive_keys=["account_number", "ssn"])
    record = _make_record(msg="custom")
    setattr(record, "account_number", "12345678")
    setattr(record, "ssn", "999-99-9999")
    setattr(record, "user_id", "u-1")

    flt.filter(record)

    assert getattr(record, "account_number") == "***"
    assert getattr(record, "ssn") == "***"
    assert getattr(record, "user_id") == "u-1"


def test_redaction_filter_does_not_touch_standard_fields() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="standard")
    original_name = record.name
    original_levelname = record.levelname

    flt.filter(record)

    assert record.name == original_name
    assert record.levelname == original_levelname


def test_redaction_filter_key_matching_is_case_insensitive() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="case")
    setattr(record, "PASSWORD", "abc")
    setattr(record, "Token", "xyz")

    flt.filter(record)

    assert getattr(record, "PASSWORD") == "***"
    assert getattr(record, "Token") == "***"


def test_redaction_filter_recursively_masks_nested_dict_keys() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="nested")
    setattr(
        record,
        "payload",
        {"password": "secret", "nested": {"token": "abc", "safe": "ok"}},
    )

    flt.filter(record)

    assert getattr(record, "payload") == {
        "password": "***",
        "nested": {"token": "***", "safe": "ok"},
    }


def test_redaction_filter_recursively_masks_deeply_nested_dict_keys() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="deep")
    setattr(
        record,
        "context",
        {"level_1": {"level_2": {"authorization": "Bearer x", "value": 42}}},
    )

    flt.filter(record)

    assert getattr(record, "context") == {
        "level_1": {"level_2": {"authorization": "***", "value": 42}}
    }


def test_redaction_filter_recursively_masks_dicts_inside_lists() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="list")
    setattr(
        record,
        "events",
        [{"token": "abc"}, {"safe": "value"}, {"authorization": "Bearer y"}],
    )

    flt.filter(record)

    assert getattr(record, "events") == [
        {"token": "***"},
        {"safe": "value"},
        {"authorization": "***"},
    ]


def test_redaction_filter_recursively_masks_mixed_nested_structures() -> None:
    flt = RedactionFilter()
    record = _make_record(msg="mixed")
    setattr(
        record,
        "metadata",
        {
            "items": [
                {"secret": "s-1", "nested": [{"api_key": "k-1"}, {"safe": "ok"}]},
                "raw",
            ],
            "profile": {"passwd": "p-1", "name": "alice"},
        },
    )

    flt.filter(record)

    assert getattr(record, "metadata") == {
        "items": [
            {"secret": "***", "nested": [{"api_key": "***"}, {"safe": "ok"}]},
            "raw",
        ],
        "profile": {"passwd": "***", "name": "alice"},
    }


def test_redaction_filter_skips_attributes_that_raise_on_access() -> None:
    class ExplodingRecord(logging.LogRecord):
        def __getattribute__(self, name: str) -> object:
            if name == "explode":
                msg = "attribute access failure"
                raise RuntimeError(msg)
            return super().__getattribute__(name)

    flt = RedactionFilter()
    record = ExplodingRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="exploding",
        args=(),
        exc_info=None,
    )
    setattr(record, "explode", {"token": "abc"})
    setattr(record, "password", "s3cr3t")
    setattr(record, "payload", {"token": "abc", "safe": "ok"})

    assert flt.filter(record) is True
    assert record.__dict__["explode"] == {"token": "***"}
    assert getattr(record, "password") == "***"
    assert getattr(record, "payload") == {"token": "***", "safe": "ok"}


class TestSamplingFilterNameScoping:
    """Tests for name-based filter scoping in SamplingFilter."""

    def test_non_matching_logger_bypasses_sampling(self) -> None:
        """Records from non-matching loggers pass through without sampling."""
        flt = SamplingFilter(rate=1, name="myapp")
        # Record from a different logger
        record = logging.LogRecord(
            name="other.module",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        # Should pass through even though rate=1 — name doesn't match
        assert flt.filter(record) is True
        assert flt.filter(record) is True  # not rate-limited

    def test_matching_logger_applies_sampling(self) -> None:
        """Records from matching loggers are subject to sampling."""
        flt = SamplingFilter(rate=1, name="myapp")
        record = logging.LogRecord(
            name="myapp.sub",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        assert flt.filter(record) is True  # first passes
        assert flt.filter(record) is False  # second is rate-limited


class TestRedactionFilterHardening:
    """Tests for cycle guard, depth limit, and catch-all exception handling."""

    def test_cyclic_dict_does_not_raise(self) -> None:
        flt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        cyclic: dict[str, object] = {"a": 1}
        cyclic["self"] = cyclic  # self-reference
        record.__dict__["payload"] = cyclic
        # Must not raise, must return True
        assert flt.filter(record) is True

    def test_deeply_nested_dict_is_handled_gracefully(self) -> None:
        from azure_functions_logging._filters import _REDACT_MAX_DEPTH

        flt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        # Build a dict nested deeper than the limit
        deep: dict[str, object] = {}
        node = deep
        for _ in range(_REDACT_MAX_DEPTH + 5):
            child: dict[str, object] = {}
            node["next"] = child
            node = child
        record.__dict__["deep"] = deep
        assert flt.filter(record) is True  # must not raise

    def test_cyclic_list_does_not_raise(self) -> None:
        flt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        cyclic_list: list[object] = [1, 2]
        cyclic_list.append(cyclic_list)  # self-reference
        record.__dict__["items"] = cyclic_list
        assert flt.filter(record) is True

    def test_malformed_payload_does_not_crash_filter(self) -> None:
        """A __iter__ that raises must not crash the filter."""

        class ExplodingDict(dict[str, object]):
            def items(self) -> object:  # type: ignore[override]
                msg = "boom"
                raise RuntimeError(msg)

        flt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.__dict__["broken"] = ExplodingDict({"password": "secret"})
        assert flt.filter(record) is True  # catch-all must swallow the error


class TestRedactionFilterNameScoping:
    """Tests for name-based filter scoping in RedactionFilter."""

    def test_non_matching_logger_bypasses_redaction(self) -> None:
        """Records from non-matching loggers are not redacted."""
        flt = RedactionFilter(name="myapp")
        record = logging.LogRecord(
            name="other.module",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        setattr(record, "password", "secret123")
        assert flt.filter(record) is True
        assert getattr(record, "password") == "secret123"  # not redacted

    def test_matching_logger_applies_redaction(self) -> None:
        """Records from matching loggers are redacted."""
        flt = RedactionFilter(name="myapp")
        record = logging.LogRecord(
            name="myapp.handler",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        setattr(record, "password", "secret123")
        assert flt.filter(record) is True
        assert getattr(record, "password") == "***"


def test_redact_value_at_depth_limit_is_masked_not_returned() -> None:
    """At _REDACT_MAX_DEPTH the function must return the mask string (fail-closed)
    rather than the original value, so sensitive data buried below the depth
    limit cannot leak through unredacted."""
    from azure_functions_logging._filters import _REDACT_MAX_DEPTH, _redact_value

    sensitive: frozenset[str] = frozenset({"password"})
    payload = {"safe_key": "safe_value"}  # non-sensitive; would pass through without limit
    result = _redact_value(payload, sensitive, _depth=_REDACT_MAX_DEPTH)
    assert result == "***", f"Expected mask at depth limit but got: {result!r}"


def test_redaction_filter_field_setattr_error_does_not_stop_subsequent_field_redaction() -> None:
    """If setattr() raises for one field (e.g. a read-only class descriptor), the
    per-field try/except must catch the error so subsequent sensitive fields are still
    redacted on the same record."""

    class _RecordWithReadOnlyToken(logging.LogRecord):
        """LogRecord subclass where setting 'token' raises AttributeError."""

    class _ReadOnlyDescriptor:
        def __get__(self, obj: object, objtype: object = None) -> str:
            return "secret_token_value"

        def __set__(self, obj: object, value: object) -> None:
            msg = "token is read-only on this record subclass"
            raise AttributeError(msg)

    _RecordWithReadOnlyToken.token = _ReadOnlyDescriptor()  # type: ignore[attr-defined]

    flt = RedactionFilter()
    record = _RecordWithReadOnlyToken(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="msg", args=(), exc_info=None,
    )
    # Bypass the descriptor to seed 'token' into __dict__ so the filter iterates it
    record.__dict__["token"] = "secret_token_value"
    # Place 'password' AFTER 'token' so it only gets redacted if the loop continues
    record.__dict__["password"] = "should_be_redacted"

    assert flt.filter(record) is True
    assert record.__dict__.get("password") == "***", (
        f"Expected password to be redacted after broken token field; "
        f"got: {record.__dict__.get('password')!r}"
    )


# ---------------------------------------------------------------------------
# RedactionFilter — default sensitive keys: Azure credential fields
# ---------------------------------------------------------------------------


def test_redaction_filter_masks_access_token() -> None:
    flt = RedactionFilter()
    record = _make_record()
    setattr(record, "access_token", "eyJ...")
    flt.filter(record)
    assert getattr(record, "access_token") == "***"


def test_redaction_filter_masks_refresh_token() -> None:
    flt = RedactionFilter()
    record = _make_record()
    setattr(record, "refresh_token", "rt_abc")
    flt.filter(record)
    assert getattr(record, "refresh_token") == "***"


def test_redaction_filter_masks_client_secret() -> None:
    flt = RedactionFilter()
    record = _make_record()
    setattr(record, "client_secret", "cs_xyz")
    flt.filter(record)
    assert getattr(record, "client_secret") == "***"


def test_redaction_filter_masks_connection_string() -> None:
    flt = RedactionFilter()
    record = _make_record()
    setattr(record, "connection_string", "DefaultEndpointsProtocol=https;AccountName=...")
    flt.filter(record)
    assert getattr(record, "connection_string") == "***"


def test_redaction_filter_masks_new_keys_inside_nested_dict() -> None:
    """New default keys must be redacted inside nested dicts, not just at top level."""
    flt = RedactionFilter()
    record = _make_record()
    setattr(record, "credentials", {
        "access_token": "tok-1",
        "refresh_token": "rt-1",
        "client_secret": "cs-1",
        "connection_string": "conn-1",
        "safe_field": "visible",
    })
    flt.filter(record)
    assert getattr(record, "credentials") == {
        "access_token": "***",
        "refresh_token": "***",
        "client_secret": "***",
        "connection_string": "***",
        "safe_field": "visible",
    }


def test_redaction_filter_masks_new_keys_inside_list_of_dicts() -> None:
    """New default keys must be redacted inside lists of dicts."""
    flt = RedactionFilter()
    record = _make_record()
    setattr(record, "items", [
        {"access_token": "tok-a", "user": "alice"},
        {"refresh_token": "rt-b", "client_secret": "cs-b"},
        {"connection_string": "conn-c", "safe": "ok"},
    ])
    flt.filter(record)
    assert getattr(record, "items") == [
        {"access_token": "***", "user": "alice"},
        {"refresh_token": "***", "client_secret": "***"},
        {"connection_string": "***", "safe": "ok"},
    ]


def test_redaction_filter_new_keys_case_insensitive() -> None:
    """New default keys must match case-insensitively."""
    flt = RedactionFilter()
    record = _make_record()
    setattr(record, "Access_Token", "tok")
    setattr(record, "CONNECTION_STRING", "cs")
    flt.filter(record)
    assert getattr(record, "Access_Token") == "***"
    assert getattr(record, "CONNECTION_STRING") == "***"
