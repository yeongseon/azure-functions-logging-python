from __future__ import annotations

from collections.abc import Iterator
import json
import logging

import pytest

from azure_functions_logging._host_instance import (
    _INSTANCE_ENV_VARS,
    _reset_host_instance_id_cache,
    get_host_instance_id,
)
from azure_functions_logging._json_formatter import JsonFormatter, _emergency_payload

_ALL_INSTANCE_ENV_VARS = (*_INSTANCE_ENV_VARS, "HOSTNAME")


@pytest.fixture(autouse=True)
def _clear_cache_and_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate each test: clear the per-process cache and all instance env vars."""
    for name in _ALL_INSTANCE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    _reset_host_instance_id_cache()
    yield
    _reset_host_instance_id_cache()


def test_website_instance_id_has_highest_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "web-instance-1")
    monkeypatch.setenv("WEBSITE_POD_NAME", "pod-1")
    monkeypatch.setenv("CONTAINER_NAME", "container-1")
    assert get_host_instance_id() == "web-instance-1"


def test_website_pod_name_used_when_instance_id_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_POD_NAME", "pod-2")
    monkeypatch.setenv("CONTAINER_NAME", "container-2")
    assert get_host_instance_id() == "pod-2"


def test_container_name_used_when_higher_priority_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTAINER_NAME", "container-3")
    assert get_host_instance_id() == "container-3"


def test_empty_env_values_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "")
    monkeypatch.setenv("WEBSITE_POD_NAME", "")
    monkeypatch.setenv("CONTAINER_NAME", "container-4")
    assert get_host_instance_id() == "container-4"


def test_falls_back_to_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("socket.gethostname", lambda: "my-hostname")
    assert get_host_instance_id() == "my-hostname"


def test_returns_none_when_all_sources_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("socket.gethostname", lambda: "")
    assert get_host_instance_id() is None


def test_resolution_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> str:
        raise OSError("no hostname")

    monkeypatch.setattr("socket.gethostname", _boom)
    assert get_host_instance_id() is None


def test_value_is_cached_within_same_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "cached-1")
    assert get_host_instance_id() == "cached-1"
    # Changing the env after the first resolution must NOT change the cached value.
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "cached-2")
    assert get_host_instance_id() == "cached-1"


def test_cache_recomputes_when_pid_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "pid-original")
    assert get_host_instance_id() == "pid-original"

    # Simulate a forked worker: same module globals, different PID.
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "pid-forked")
    monkeypatch.setattr("os.getpid", lambda: 999_999)
    assert get_host_instance_id() == "pid-forked"


def test_reset_cache_forces_recomputation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "before-reset")
    assert get_host_instance_id() == "before-reset"
    _reset_host_instance_id_cache()
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "after-reset")
    assert get_host_instance_id() == "after-reset"


def test_json_payload_includes_host_instance_id_from_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "resolver-fallback")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hi",
        args=(),
        exc_info=None,
    )
    record.host_instance_id = "stamped-on-record"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["host_instance_id"] == "stamped-on-record"


def test_json_payload_falls_back_to_resolver_when_record_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "resolver-value")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hi",
        args=(),
        exc_info=None,
    )
    # No host_instance_id attribute set — formatter resolves directly.
    payload = json.loads(JsonFormatter().format(record))
    assert payload["host_instance_id"] == "resolver-value"


def test_emergency_payload_includes_host_instance_id() -> None:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="boom",
        args=(),
        exc_info=None,
    )
    payload = json.loads(_emergency_payload(record))
    assert payload["host_instance_id"] is None
