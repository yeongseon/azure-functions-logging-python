from __future__ import annotations

import re

from azure_functions_logging._redaction import is_sensitive, mask_patterns, mask_value


def test_is_sensitive_when_key_uses_header_case() -> None:
    key = "X-Functions-Key"

    result = is_sensitive(key)

    assert result is True


def test_is_sensitive_when_key_uses_camel_case() -> None:
    key = "xFunctionsKey"

    result = is_sensitive(key)

    assert result is True


def test_mask_value_when_nested_segment_is_sensitive() -> None:
    payload = {"hint": "first pet"}

    result = mask_value("account.password", payload)

    assert result == "***"


def test_mask_patterns_when_message_contains_secret_prefix() -> None:
    message = "connecting with token=ghp_abcdefghijklmnopqrstuvwxyz"

    result = mask_patterns(message)

    assert result == "connecting with token=***"


def test_mask_patterns_when_custom_pattern_has_no_keep_group() -> None:
    patterns = (re.compile(r"secret-[0-9]+"),)

    result = mask_patterns("value secret-42", patterns=patterns, mask="[MASKED]")

    assert result == "value [MASKED]"
