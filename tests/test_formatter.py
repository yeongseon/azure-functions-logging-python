from __future__ import annotations

import logging
import sys

import pytest

from azure_functions_logging._formatter import ColorFormatter


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


def test_basic_format_output_contains_time_level_name_message() -> None:
    formatter = ColorFormatter()
    record = _make_record(logging.INFO, "basic message")

    output = formatter.format(record)

    assert "test.logger" in output
    assert "basic message" in output
    assert "INFO" in output


def test_context_fields_appended_when_present() -> None:
    formatter = ColorFormatter()
    record = _make_record(msg="with context")
    record.invocation_id = "inv-1"
    record.function_name = "fn-1"
    record.trace_id = "trace-1"

    output = formatter.format(record)

    assert "invocation_id=inv-1" in output
    assert "function_name=fn-1" in output
    assert "trace_id=trace-1" in output


def test_cold_start_shown_only_when_true() -> None:
    formatter = ColorFormatter()
    record_true = _make_record(msg="cold")
    record_true.cold_start = True

    output_true = formatter.format(record_true)
    assert "cold_start=true" in output_true

    record_false = _make_record(msg="warm")
    record_false.cold_start = False
    output_false = formatter.format(record_false)
    assert "cold_start=true" not in output_false

    record_none = _make_record(msg="none")
    record_none.cold_start = None
    output_none = formatter.format(record_none)
    assert "cold_start=true" not in output_none


def test_exception_info_is_included() -> None:
    formatter = ColorFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=None,
        )
        record.exc_info = sys.exc_info()

    output = formatter.format(record)

    assert "Traceback" in output
    assert "ValueError: boom" in output


def test_is_tty_returns_bool() -> None:
    result = ColorFormatter.is_tty()
    assert isinstance(result, bool)


def test_include_extra_shows_bind_context_fields() -> None:
    formatter = ColorFormatter(include_extra=True)
    record = _make_record(msg="with extra")
    setattr(record, "user_id", "user-1")
    setattr(record, "request_id", "req-123")

    output = formatter.format(record)

    assert "user_id=user-1" in output
    assert "request_id=req-123" in output


def test_include_extra_masks_sensitive_keys() -> None:
    formatter = ColorFormatter(include_extra=True)
    record = _make_record(msg="sensitive")
    setattr(record, "password", "s3cr3t")
    setattr(record, "token", "tok123")
    setattr(record, "authorization", "Bearer xyz")

    output = formatter.format(record)

    assert "s3cr3t" not in output
    assert "tok123" not in output
    assert "Bearer xyz" not in output
    assert "password=***" in output
    assert "token=***" in output
    assert "authorization=***" in output


def test_include_extra_masks_shared_redaction_keys() -> None:
    # Guards the coupling to the shared _redaction rules: keys beyond the
    # legacy hardcoded set (access_token) and hyphenated header forms
    # (X-Functions-Key) must be masked via mask_value().
    formatter = ColorFormatter(include_extra=True)
    record = _make_record(msg="sensitive")
    setattr(record, "access_token", "at-secret")
    setattr(record, "X-Functions-Key", "fk-secret")

    output = formatter.format(record)

    assert "at-secret" not in output
    assert "fk-secret" not in output
    assert "access_token=***" in output
    assert "X-Functions-Key=***" in output


def test_include_extra_false_by_default_hides_extra_fields() -> None:
    formatter = ColorFormatter()  # include_extra defaults to False
    record = _make_record(msg="no extra")
    setattr(record, "user_id", "should-not-appear")

    output = formatter.format(record)

    assert "user_id" not in output
    assert "should-not-appear" not in output


def test_include_extra_with_allowlist_filters_keys() -> None:
    formatter = ColorFormatter(include_extra=True, extra_allowlist=["user_id"])
    record = _make_record(msg="allowlist")
    setattr(record, "user_id", "u1")
    setattr(record, "request_id", "r1")

    output = formatter.format(record)

    assert "user_id=u1" in output
    assert "request_id" not in output


def test_non_tty_output_has_no_ansi_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ColorFormatter, "is_tty", staticmethod(lambda: False))
    monkeypatch.delenv("NO_COLOR", raising=False)
    formatter = ColorFormatter()

    output = formatter.format(_make_record(msg="piped"))

    assert "\033" not in output
    assert "INFO" in output


def test_no_color_env_suppresses_color_even_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ColorFormatter, "is_tty", staticmethod(lambda: True))
    monkeypatch.setenv("NO_COLOR", "1")
    formatter = ColorFormatter()

    output = formatter.format(_make_record(msg="no color"))

    assert "\033" not in output


def test_interactive_tty_without_no_color_colorizes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ColorFormatter, "is_tty", staticmethod(lambda: True))
    monkeypatch.delenv("NO_COLOR", raising=False)
    formatter = ColorFormatter()

    output = formatter.format(_make_record(msg="colored"))

    assert "\033" in output


def test_no_color_empty_string_still_suppresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ColorFormatter, "is_tty", staticmethod(lambda: True))
    monkeypatch.setenv("NO_COLOR", "")
    formatter = ColorFormatter()

    output = formatter.format(_make_record(msg="empty no color"))

    assert "\033" not in output
