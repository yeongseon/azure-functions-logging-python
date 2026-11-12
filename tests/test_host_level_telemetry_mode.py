"""host.json level-conflict diagnostics by telemetry mode (offline, no network).

Behavior follows Microsoft Learn "Use OpenTelemetry with Azure Functions": in
``telemetryMode: OpenTelemetry`` host.json filters govern host-process logs only,
while the Python worker streams (or is filtered) through OpenTelemetry settings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import warnings

import pytest

from azure_functions_logging._host_config import (
    _env_flag_enabled,
    _python_worker_exports_otel_directly,
    warn_host_json_level_conflict,
    warn_otel_logging_misconfig,
)

_ENV = (
    "PYTHON_ENABLE_OPENTELEMETRY",
    "PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY",
    "OTEL_LOGS_EXPORTER",
    "OTEL_TRACES_EXPORTER",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "AZURE_MONITOR_CONNECTION_STRING",
)
_WARNING_HOST = {"logging": {"logLevel": {"default": "Warning"}}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def _host(tmp_path: Path, content: dict[str, object]) -> Path:
    path = tmp_path / "host.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def _warnings_for(host: Path) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO, host_json_path=host)
    return [str(w.message) for w in caught]


@pytest.mark.parametrize(
    ("mode", "env", "expect_warning"),
    [
        (None, {}, True),  # unknown mode: legacy behavior
        ("ApplicationInsights", {}, True),  # classic-like value: legacy behavior
        (None, {"PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY": "true"}, True),  # flag w/o OTel mode
        ("OpenTelemetry", {}, True),  # host exports forwarded worker logs: filter applies
        ("opentelemetry", {"PYTHON_ENABLE_OPENTELEMETRY": "false"}, True),  # disabled flag
        ("OpenTelemetry", {"PYTHON_ENABLE_OPENTELEMETRY": "0"}, True),
        ("OpenTelemetry", {"PYTHON_ENABLE_OPENTELEMETRY": "true"}, False),  # worker-direct
        ("OpenTelemetry", {"PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY": "True"}, False),
        ("OpenTelemetry", {"PYTHON_ENABLE_OPENTELEMETRY": "1"}, False),
    ],
)
def test_host_level_warning_by_telemetry_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str | None,
    env: dict[str, str],
    expect_warning: bool,
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    content: dict[str, object] = dict(_WARNING_HOST)
    if mode is not None:
        content["telemetryMode"] = mode
    messages = _warnings_for(_host(tmp_path, content))
    assert bool(messages) is expect_warning
    if expect_warning:
        assert "more restrictive" in messages[0]


def test_app_setting_override_is_also_host_process_scoped_in_worker_direct_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AzureFunctionsJobHost__logging__logLevel__default", "Error")
    monkeypatch.setenv("PYTHON_ENABLE_OPENTELEMETRY", "true")
    assert _warnings_for(_host(tmp_path, {"telemetryMode": "OpenTelemetry"})) == []


def test_app_setting_override_still_warns_in_classic_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AzureFunctionsJobHost__logging__logLevel__default", "Error")
    assert len(_warnings_for(_host(tmp_path, {"version": "2.0"}))) == 1


def test_otel_provider_section_is_checked_in_otel_mode_without_direct_export(
    tmp_path: Path,
) -> None:
    host = _host(
        tmp_path,
        {
            "telemetryMode": "OpenTelemetry",
            "logging": {"OpenTelemetry": {"logLevel": {"default": "Warning"}}},
        },
    )
    messages = _warnings_for(host)
    assert len(messages) == 1 and "'Warning'" in messages[0]


def test_otel_provider_section_is_ignored_outside_otel_mode(tmp_path: Path) -> None:
    host = _host(tmp_path, {"logging": {"OpenTelemetry": {"logLevel": {"default": "Warning"}}}})
    assert _warnings_for(host) == []


def test_otel_provider_section_overrides_general_section(tmp_path: Path) -> None:
    host = _host(
        tmp_path,
        {
            "telemetryMode": "OpenTelemetry",
            "logging": {
                "logLevel": {"default": "Warning"},
                "OpenTelemetry": {"logLevel": {"default": "Information"}},
            },
        },
    )
    assert _warnings_for(host) == []


def test_malformed_otel_provider_section_is_ignored(tmp_path: Path) -> None:
    host = _host(tmp_path, {"telemetryMode": "OpenTelemetry", "logging": {"OpenTelemetry": 3}})
    assert _warnings_for(host) == []


def test_missing_explicit_host_json_stays_silent_even_with_discovery_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _host(tmp_path, {"telemetryMode": "OpenTelemetry", **_WARNING_HOST})
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO, host_json_path=tmp_path / "missing.json")
    assert caught == []


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        (" yes ", True),
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("off", False),
        ("", False),
    ],
)
def test_env_flag_enabled_values(
    monkeypatch: pytest.MonkeyPatch, value: str, enabled: bool
) -> None:
    monkeypatch.setenv("PYTHON_ENABLE_OPENTELEMETRY", value)
    assert _env_flag_enabled("PYTHON_ENABLE_OPENTELEMETRY") is enabled
    assert _python_worker_exports_otel_directly() is enabled


def test_env_flag_absent_is_disabled() -> None:
    assert _env_flag_enabled("PYTHON_ENABLE_OPENTELEMETRY") is False


class _OtelHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        pass


_OtelHandler.__module__ = "opentelemetry.sdk._logs._internal"


@pytest.mark.parametrize(
    ("env", "warns"),
    [
        ({}, True),  # no signal
        ({"PYTHON_ENABLE_OPENTELEMETRY": "false"}, True),  # explicitly disabled is not a signal
        ({"PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY": "0"}, True),
        ({"PYTHON_ENABLE_OPENTELEMETRY": "true"}, False),
        ({"OTEL_LOGS_EXPORTER": "otlp"}, False),
        ({"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=x"}, False),
        ({"PYTHON_ENABLE_OPENTELEMETRY": "false", "OTEL_LOGS_EXPORTER": "otlp"}, False),
    ],
)
def test_6b_export_signal_matrix(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], warns: bool
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    root = logging.getLogger()
    handler = _OtelHandler()
    root.addHandler(handler)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warn_otel_logging_misconfig()
    finally:
        root.removeHandler(handler)
    assert any("neither" in str(w.message) for w in caught) is warns
