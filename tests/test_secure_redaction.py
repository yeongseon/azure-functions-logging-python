"""Fail-closed boundary contracts; all credentials are synthetic canaries."""

from collections import UserDict
import logging
import re
import sys
from typing import NoReturn

import pytest

from azure_functions_logging import DEFAULT_REDACTION_PATTERNS, RedactionFilter

CANARY = "CANARY_SECRET_BOUNDARY"


class BrokenMapping(dict[str, object]):
    def items(self) -> NoReturn:
        raise RuntimeError(CANARY)


class BrokenRendering:
    def __str__(self) -> str:
        raise RuntimeError(CANARY)

    def __repr__(self) -> str:
        raise RuntimeError(CANARY)


class SecretRendering:
    def __str__(self) -> str:
        return CANARY

    def __repr__(self) -> str:
        return f"Bearer {CANARY}"


def test_field_failure_masks_value_when_fail_closed() -> None:
    # Given: iteration fails before a nested credential can be inspected.
    record = logging.makeLogRecord({"msg": "ordinary", "payload": BrokenMapping(token=CANARY)})
    flt = RedactionFilter(fail_closed=True)
    # When
    accepted = flt.filter(record)
    # Then
    assert accepted is True
    assert record.__dict__["payload"] == "***"


def test_default_failure_retains_original_value() -> None:
    # Given: the deliberate legacy fail-open contract.
    value = BrokenMapping(token=CANARY)
    record = logging.makeLogRecord({"msg": "ordinary", "payload": value})
    # When
    RedactionFilter().filter(record)
    # Then
    assert record.__dict__["payload"] is value


def test_message_failure_drops_original_diagnostics_when_fail_closed() -> None:
    # Given
    record = logging.makeLogRecord(
        {
            "msg": "value %s",
            "args": (BrokenRendering(),),
            "stack_info": CANARY,
            "exc_text": CANARY,
            "exception.message": f"token={CANARY}",
        }
    )
    # When
    accepted = RedactionFilter(fail_closed=True).filter(record)
    # Then
    assert accepted is True
    assert record.getMessage() == "[REDACTION FAILED]"
    assert record.args == ()
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.stack_info is None
    assert CANARY not in repr(record.__dict__)


@pytest.mark.parametrize("value", [BrokenRendering(), SecretRendering()])
def test_custom_object_is_replaced_by_safe_rendering(value: object) -> None:
    # Given
    record = logging.makeLogRecord({"msg": "ordinary", "payload": value})
    # When
    RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS, fail_closed=True).filter(record)
    # Then
    assert isinstance(record.__dict__["payload"], str)
    assert CANARY not in repr(record.__dict__)


def test_mapping_sets_tuples_and_non_string_keys_are_sanitized() -> None:
    # Given
    record = logging.makeLogRecord(
        {
            "msg": "ordinary",
            "payload": UserDict(
                {
                    "headers": UserDict({"AUTHORIZATION": CANARY, "X-Functions-Key": CANARY}),
                    7: ({f"Bearer {CANARY}"}, {"token": CANARY}),
                    SecretRendering(): f"password={CANARY}",
                }
            ),
        }
    )
    # When
    RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS, fail_closed=True).filter(record)
    # Then
    assert CANARY not in repr(record.__dict__)
    assert record.__dict__["payload"]["headers"]["AUTHORIZATION"] == "***"


def test_pattern_failure_masks_instead_of_skipping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a substitution boundary failure, not an invalid constructor regex.
    flt = RedactionFilter(patterns=[re.compile("canary")], fail_closed=True)
    record = logging.makeLogRecord({"msg": CANARY, "payload": CANARY})

    def broken(*args: object) -> str:
        raise RuntimeError(CANARY)

    monkeypatch.setattr("azure_functions_logging._secure_values.mask_text", broken)
    # When
    accepted = flt.filter(record)
    # Then
    assert accepted is True
    assert record.__dict__["payload"] == "***"
    assert record.getMessage() == "[REDACTION FAILED]"


def test_exception_failure_removes_raw_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    try:
        raise ValueError(f"password={CANARY}")
    except ValueError:
        info = sys.exc_info()
    record = logging.makeLogRecord({"msg": "ordinary", "exc_info": info})

    def broken(*args: object) -> str:
        raise RuntimeError(CANARY)

    monkeypatch.setattr("traceback.format_exception", broken)
    # When
    accepted = RedactionFilter(fail_closed=True).filter(record)
    # Then
    assert accepted is True
    assert record.exc_info is None
    assert record.exc_text == "***"
    assert CANARY not in repr(record.__dict__)


def test_structured_message_masks_nested_keys() -> None:
    # Given
    record = logging.makeLogRecord({"msg": {"token": CANARY, "count": 7}})
    # When
    RedactionFilter(fail_closed=True).filter(record)
    # Then
    assert CANARY not in repr(record.__dict__)


def test_benign_json_message_keeps_original_whitespace() -> None:
    # Given
    text = '{ "count": 7, "enabled": true }'
    record = logging.makeLogRecord({"msg": text})
    # When
    RedactionFilter(fail_closed=True).filter(record)
    # Then
    assert record.getMessage() == text


def test_json_message_masks_sensitive_keys() -> None:
    # Given
    record = logging.makeLogRecord({"msg": '{"token":"' + CANARY + '"}'})
    # When
    RedactionFilter(fail_closed=True).filter(record)
    # Then
    assert record.getMessage() == '{"token":"***"}'


def test_cached_exception_and_stack_are_masked() -> None:
    # Given
    record = logging.makeLogRecord(
        {"msg": "ordinary", "exc_text": f"token={CANARY}", "stack_info": f"password={CANARY}"}
    )
    # When
    RedactionFilter(fail_closed=True).filter(record)
    # Then
    assert record.exc_text == "token=***"
    assert record.stack_info == "password=***"


def test_cached_message_is_replaced_after_render_failure() -> None:
    # Given
    record = logging.makeLogRecord({"msg": BrokenRendering(), "message": CANARY})
    flt = RedactionFilter(fail_closed=True)

    def broken() -> str:
        raise RuntimeError(CANARY)

    setattr(record, "getMessage", broken)
    # When
    flt.filter(record)
    # Then
    assert record.__dict__["message"] == "[REDACTION FAILED]"


def test_fail_closed_still_honors_explicit_name_scope() -> None:
    # Given
    record = logging.LogRecord("other.child", logging.INFO, "", 1, CANARY, (), None)
    record.__dict__["token"] = CANARY
    # When
    RedactionFilter(name="selected", fail_closed=True).filter(record)
    # Then
    assert record.__dict__["token"] == CANARY
