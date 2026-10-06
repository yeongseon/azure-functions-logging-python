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


def _host_log(invocation_id: str, propagated_id: str | None = None) -> str:
    records = (
        {"invocation_id": invocation_id, "extra": {"marker": "corr-main-1"}},
        {"invocation_id": invocation_id, "extra": {"marker": "corr-main-2"}},
        {
            "invocation_id": propagated_id or invocation_id,
            "extra": {"marker": "corr-thread-propagated"},
        },
    )
    return "\n".join(json.dumps(record) for record in records)


def _response(invocation_id: str | None = None) -> str:
    return json.dumps(
        {
            "thread_records": [
                {
                    "invocation_id": invocation_id,
                    "extra": {"marker": "corr-thread-unpropagated"},
                }
            ]
        }
    )


def test_check_accepts_unpropagated_and_propagated_thread_controls() -> None:
    # Given
    assertion = _load_assertion()
    invocation_id = "03550af5-127c-4b41-a9a5-c3a0a990c518"

    # When
    failures = assertion.check(_host_log(invocation_id), _response())

    # Then
    assert failures == []


def test_check_rejects_unpropagated_thread_with_invocation_id() -> None:
    # Given
    assertion = _load_assertion()
    invocation_id = "03550af5-127c-4b41-a9a5-c3a0a990c518"
    # When
    failures = assertion.check(_host_log(invocation_id), _response(invocation_id))

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
    host_log = _host_log(invocation_id, "b80e6edc-d175-4bc3-a5ef-e24d05a24e08")
    failures = assertion.check(host_log, _response())

    # Then
    assert failures == [
        "'corr-thread-propagated' invocation_id differs from the request: "
        "'b80e6edc-d175-4bc3-a5ef-e24d05a24e08' != "
        "'03550af5-127c-4b41-a9a5-c3a0a990c518'"
    ]


def test_check_rejects_missing_propagated_host_record() -> None:
    # Given
    assertion = _load_assertion()
    invocation_id = "03550af5-127c-4b41-a9a5-c3a0a990c518"
    host_log = "\n".join(_host_log(invocation_id).splitlines()[:2])

    # When
    failures = assertion.check(host_log, _response())

    # Then
    assert failures == ["no record found with marker 'corr-thread-propagated'"]
