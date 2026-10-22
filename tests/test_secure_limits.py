"""Adversarial synthetic payloads and no-collateral-damage contracts."""

from collections import UserDict
import logging

import pytest

from azure_functions_logging import DEFAULT_REDACTION_PATTERNS, RedactionFilter
from azure_functions_logging._secure import _SecureRedactionFilter
from azure_functions_logging._secure_values import MAX_NODES, MAX_TEXT

CANARY = "CANARY_SECRET_LIMITS"


@pytest.mark.parametrize("prefix", ["\u202e", "\u200b", "e\u0301", "\\ud800", "\x00", "a" * 10000])
def test_unusual_unicode_does_not_bypass_credential_masking(prefix: str) -> None:
    # Given
    record = logging.makeLogRecord({"msg": f"{prefix} password={CANARY}"})
    # When
    _SecureRedactionFilter().filter(record)
    # Then
    assert CANARY not in record.getMessage()
    assert prefix in record.getMessage()


@pytest.mark.parametrize(
    "key",
    [
        "Cookie",
        "Set-Cookie",
        "Proxy-Authorization",
        "X-API-Key",
        "X-Functions-Key",
        "Ocp-Apim-Subscription-Key",
        "InstrumentationKey",
        "SharedAccessKey",
        "SharedAccessSignature",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "AzureWebJobsStorage",
        "headers.AUTHORIZATION",
        "token.raw",
        "ConnectionString",
    ],
)
def test_secure_credential_keys_mask_entire_value(key: str) -> None:
    # Given
    record = logging.makeLogRecord({"msg": "ordinary", "headers": UserDict({key: CANARY})})
    # When
    _SecureRedactionFilter().filter(record)
    # Then
    assert record.__dict__["headers"][key] == "***"


def test_confusable_keys_are_not_claimed_as_ascii_credentials() -> None:
    # Given: homographs are not Unicode case variants of ASCII credentials.
    values = {"ΤΟΚΕΝ": "greek label", "clıent_secret": "dotless label"}
    record = logging.makeLogRecord({"msg": "ordinary", "labels": values})
    # When
    _SecureRedactionFilter().filter(record)
    # Then
    assert record.__dict__["labels"] == values


@pytest.mark.parametrize(
    "text",
    [
        "token_count author secretary password_policy documentation monkey",
        "token_count=42 author=alice secretary=available password_policy=strict monkey=yes",
        "550e8400-e29b-41d4-a716-446655440000",
        "DefaultEndpointsProtocol=https;AccountName=example;EndpointSuffix=core.windows.net",
    ],
)
def test_benign_message_and_observability_are_unchanged(text: str) -> None:
    # Given
    fields = {
        "invocation_id": "inv-42",
        "function_name": "checkout",
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "correlation_id": "request-42",
        "count": 42,
        "ratio": 0.5,
        "enabled": True,
        "missing": None,
        "note": text,
    }
    record = logging.makeLogRecord({"msg": text, "levelno": logging.WARNING, **fields})
    # When
    _SecureRedactionFilter().filter(record)
    # Then
    assert record.getMessage() == text
    assert {key: record.__dict__[key] for key in fields} == fields
    assert record.levelno == logging.WARNING


@pytest.mark.parametrize(
    "text",
    [
        f"Bearer {CANARY}",
        f"AccountKey={CANARY};EndpointSuffix=example.test",
        f"https://example.test/blob?sv=1&sig={CANARY}&se=2099",
        "ghp_CANARYSECRET01234567890123456789",
        "eyJCANARYSECRET.eyJFAKEPAYLOAD.CANARYSIGNATURE",
    ],
)
def test_curated_patterns_cover_synthetic_token_families(text: str) -> None:
    # Given
    record = logging.makeLogRecord({"msg": text, "detail": text})
    # When
    _SecureRedactionFilter().filter(record)
    # Then
    assert "CANARY" not in repr(record.__dict__)


def test_cycles_and_deep_values_use_mask_without_raw_repr() -> None:
    # Given
    cycle: list[object] = [f"password={CANARY}"]
    cycle.append(cycle)
    deep: object = {"token": CANARY}
    for _ in range(1000):
        deep = [deep]
    record = logging.makeLogRecord({"msg": "ordinary", "cycle": cycle, "deep": deep})
    # When
    RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS, fail_closed=True).filter(record)
    # Then
    assert CANARY not in repr(record.__dict__)
    assert record.__dict__["cycle"] == ["password=***", "***"]


@pytest.mark.parametrize("kind", ["list", "dict", "string"])
def test_huge_values_are_bounded_and_masked(kind: str) -> None:
    # Given
    values: dict[str, object] = {
        "list": [CANARY] * (MAX_NODES + 1),
        "dict": dict.fromkeys(range(MAX_NODES + 1), CANARY),
        "string": "a" * MAX_TEXT + CANARY,
    }
    record = logging.makeLogRecord({"msg": "ordinary", "payload": values[kind]})
    # When
    _SecureRedactionFilter().filter(record)
    # Then
    assert record.__dict__["payload"] == "***"


def test_default_profile_does_not_add_secure_keys_or_object_conversion() -> None:
    # Given
    value = UserDict({"Proxy-Authorization": CANARY})
    record = logging.makeLogRecord(
        {"msg": f"Bearer {CANARY}", "headers": value, "InstrumentationKey": CANARY}
    )
    # When
    RedactionFilter().filter(record)
    # Then
    assert record.__dict__["headers"] is value
    assert record.__dict__["InstrumentationKey"] == CANARY
    assert record.getMessage() == f"Bearer {CANARY}"
