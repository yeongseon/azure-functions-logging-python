from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_assertion() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "assert_correlation.py"
    spec = importlib.util.spec_from_file_location("assert_correlation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load correlation assertion from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _host_log(invocation_id: str) -> str:
    records = (
        {"invocation_id": invocation_id, "extra": {"marker": "corr-main-1"}},
        {"invocation_id": invocation_id, "extra": {"marker": "corr-main-2"}},
    )
    return "\n".join(json.dumps(record) for record in records)


def _response(invocation_id: str, propagated_id: str | None = None) -> str:
    return json.dumps(
        {
            "thread_records": [
                {"invocation_id": None, "extra": {"marker": "corr-thread-unpropagated"}},
                {
                    "invocation_id": propagated_id or invocation_id,
                    "extra": {"marker": "corr-thread-propagated"},
                },
            ]
        }
    )


def test_check_accepts_unpropagated_and_propagated_thread_controls() -> None:
    # Given
    assertion = _load_assertion()
    invocation_id = "03550af5-127c-4b41-a9a5-c3a0a990c518"

    # When
    failures = assertion.check(_host_log(invocation_id), _response(invocation_id))

    # Then
    assert failures == []


def test_check_rejects_unpropagated_thread_with_invocation_id() -> None:
    # Given
    assertion = _load_assertion()
    invocation_id = "03550af5-127c-4b41-a9a5-c3a0a990c518"
    response = json.loads(_response(invocation_id))
    response["thread_records"][0]["invocation_id"] = invocation_id

    # When
    failures = assertion.check(_host_log(invocation_id), json.dumps(response))

    # Then
    assert failures == [
        "'corr-thread-unpropagated' unexpectedly carried an invocation_id "
        "('03550af5-127c-4b41-a9a5-c3a0a990c518'); a background thread without "
        "propagate_context must lose it"
    ]


def test_check_rejects_propagated_thread_with_different_invocation_id() -> None:
    # Given
    assertion = _load_assertion()
    invocation_id = "03550af5-127c-4b41-a9a5-c3a0a990c518"

    # When
    failures = assertion.check(
        _host_log(invocation_id),
        _response(invocation_id, "b80e6edc-d175-4bc3-a5ef-e24d05a24e08"),
    )

    # Then
    assert failures == [
        "'corr-thread-propagated' invocation_id differs from the request: "
        "'b80e6edc-d175-4bc3-a5ef-e24d05a24e08' != "
        "'03550af5-127c-4b41-a9a5-c3a0a990c518'"
    ]
