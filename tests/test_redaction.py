from __future__ import annotations

import re

from azure_functions_logging._redaction import is_sensitive, mask_patterns, mask_value


def test_is_sensitive_when_key_uses_header_case() -> None:
    # Given
    key = "X-Functions-Key"

    # When
    result = is_sensitive(key)

    # Then
    assert result is True


def test_is_sensitive_when_key_uses_camel_case() -> None:
    # Given
    key = "xFunctionsKey"

    # When
    result = is_sensitive(key)

    # Then
    assert result is True


def test_mask_value_when_nested_segment_is_sensitive() -> None:
    # Given
    payload = {"hint": "first pet"}

    # When
    result = mask_value("account.password", payload)

    # Then
    assert result == "***"


def test_mask_patterns_when_message_contains_secret_prefix() -> None:
    # Given
    message = "connecting with token=ghp_abcdefghijklmnopqrstuvwxyz"

    # When
    result = mask_patterns(message)

    # Then
    assert result == "connecting with token=***"


def test_mask_patterns_when_custom_pattern_has_no_keep_group() -> None:
    # Given
    patterns = (re.compile(r"secret-[0-9]+"),)

    # When
    result = mask_patterns("value secret-42", patterns=patterns, mask="[MASKED]")

    # Then
    assert result == "value [MASKED]"
