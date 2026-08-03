"""Tests for OpenTelemetry logging misconfiguration warnings (issue #256).

These cover ``warn_otel_logging_misconfig`` and its import-free helpers:

- **6a** — OTel handler present *and* ``functions_formatter`` supplied → warn ignored.
- **6b** — OTel handler present but no telemetry env var set → tentative warning.
- **6c** — ``host.json`` requests OpenTelemetry mode but no OTel handler → ordering hint.

A key requirement is **no false positives** in the wrong-call-order scenario:
when no OTel handler is attached and ``host.json`` does not request OpenTelemetry,
the function must stay silent regardless of ``functions_formatter``.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import logging
from pathlib import Path
import warnings

import pytest

from azure_functions_logging._host_config import (
    _has_otel_logging_handler,
    _read_host_telemetry_mode,
    warn_otel_logging_misconfig,
)


def _write_host_json(path: Path, content: dict[str, object]) -> None:
    path.write_text(json.dumps(content), encoding="utf-8")


class _FakeOtelHandler(logging.Handler):
    """A stand-in whose defining module mimics OpenTelemetry's SDK handler."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - no-op
        pass


# Make the import-free module-name detection treat this as an OTel handler.
_FakeOtelHandler.__module__ = "opentelemetry.sdk._logs._internal"


class _PlainHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - no-op
        pass


@pytest.fixture
def clean_root() -> Iterator[logging.Logger]:
    """Provide the root logger with its handlers/filters restored after the test."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_filters = root.filters[:]
    root.handlers = []
    root.filters = []
    try:
        yield root
    finally:
        root.handlers = saved_handlers
        root.filters = saved_filters


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure telemetry env vars are unset unless a test sets them explicitly."""
    monkeypatch.delenv("PYTHON_ENABLE_OPENTELEMETRY", raising=False)
    monkeypatch.delenv("PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY", raising=False)


# --------------------------------------------------------------------------- #
# _has_otel_logging_handler
# --------------------------------------------------------------------------- #


def test_has_otel_logging_handler_detects_otel_module(clean_root: logging.Logger) -> None:
    clean_root.addHandler(_FakeOtelHandler())
    assert _has_otel_logging_handler(clean_root) is True


def test_has_otel_logging_handler_false_for_plain_handler(clean_root: logging.Logger) -> None:
    clean_root.addHandler(_PlainHandler())
    assert _has_otel_logging_handler(clean_root) is False


def test_has_otel_logging_handler_false_when_no_handlers(clean_root: logging.Logger) -> None:
    assert _has_otel_logging_handler(clean_root) is False


# --------------------------------------------------------------------------- #
# _read_host_telemetry_mode
# --------------------------------------------------------------------------- #


def test_read_host_telemetry_mode_explicit_path(tmp_path: Path) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"telemetryMode": "OpenTelemetry"})
    assert _read_host_telemetry_mode(host) == "OpenTelemetry"


def test_read_host_telemetry_mode_missing_key(tmp_path: Path) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"version": "2.0"})
    assert _read_host_telemetry_mode(host) is None


def test_read_host_telemetry_mode_non_string(tmp_path: Path) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"telemetryMode": 123})
    assert _read_host_telemetry_mode(host) is None


def test_read_host_telemetry_mode_missing_file(tmp_path: Path) -> None:
    assert _read_host_telemetry_mode(tmp_path / "nope.json") is None


def test_read_host_telemetry_mode_malformed(tmp_path: Path) -> None:
    host = tmp_path / "host.json"
    host.write_text("not valid json", encoding="utf-8")
    assert _read_host_telemetry_mode(host) is None


def test_read_host_telemetry_mode_autodiscovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(tmp_path / "host.json", {"telemetryMode": "OpenTelemetry"})
    monkeypatch.chdir(tmp_path)
    assert _read_host_telemetry_mode(None) == "OpenTelemetry"


def test_read_host_telemetry_mode_non_mapping(tmp_path: Path) -> None:
    # A top-level JSON array is valid JSON but not a mapping.
    host = tmp_path / "host.json"
    host.write_text("[1, 2, 3]", encoding="utf-8")
    assert _read_host_telemetry_mode(host) is None


def test_read_host_telemetry_mode_oserror_on_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"telemetryMode": "OpenTelemetry"})

    def _boom(self: Path) -> bool:
        raise OSError("stat failed")

    monkeypatch.setattr(Path, "is_file", _boom)
    assert _read_host_telemetry_mode(host) is None


# --------------------------------------------------------------------------- #
# 6a — functions_formatter ignored when OTel handler present
# --------------------------------------------------------------------------- #


def test_6a_warns_when_formatter_passed_with_otel_handler(
    clean_root: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_root.addHandler(_FakeOtelHandler())
    # Set a telemetry env var so 6b stays silent; isolate 6a.
    monkeypatch.setenv("PYTHON_ENABLE_OPENTELEMETRY", "1")
    with pytest.warns(UserWarning, match="functions_formatter"):
        warn_otel_logging_misconfig(functions_formatter=logging.Formatter())


def test_6a_silent_when_no_formatter(
    clean_root: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_root.addHandler(_FakeOtelHandler())
    # env var set so 6b does not fire; only 6a is under test here.
    monkeypatch.setenv("PYTHON_ENABLE_OPENTELEMETRY", "1")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_otel_logging_misconfig(functions_formatter=None)


# --------------------------------------------------------------------------- #
# 6b — OTel handler present but no telemetry env var
# --------------------------------------------------------------------------- #


def test_6b_warns_when_no_telemetry_env_var(clean_root: logging.Logger) -> None:
    clean_root.addHandler(_FakeOtelHandler())
    with pytest.warns(UserWarning, match="may not be exported"):
        warn_otel_logging_misconfig()


@pytest.mark.parametrize(
    "env_name",
    ["PYTHON_ENABLE_OPENTELEMETRY", "PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY"],
)
def test_6b_silent_when_env_var_set(
    clean_root: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
) -> None:
    clean_root.addHandler(_FakeOtelHandler())
    monkeypatch.setenv(env_name, "1")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_otel_logging_misconfig()


# --------------------------------------------------------------------------- #
# 6c — host.json OpenTelemetry mode but no OTel handler
# --------------------------------------------------------------------------- #


def test_6c_warns_on_ordering_mismatch(
    clean_root: logging.Logger,
    tmp_path: Path,
) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"telemetryMode": "OpenTelemetry"})
    with pytest.warns(UserWarning, match="before setup_logging"):
        warn_otel_logging_misconfig(host_json_path=host)


def test_6c_case_insensitive(
    clean_root: logging.Logger,
    tmp_path: Path,
) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"telemetryMode": "opentelemetry"})
    with pytest.warns(UserWarning, match="before setup_logging"):
        warn_otel_logging_misconfig(host_json_path=host)


# --------------------------------------------------------------------------- #
# No false positives in the wrong-call-order / benign scenarios
# --------------------------------------------------------------------------- #


def test_no_warning_when_no_otel_and_no_host_mode(
    clean_root: logging.Logger,
    tmp_path: Path,
) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"version": "2.0"})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_otel_logging_misconfig(
            functions_formatter=logging.Formatter(),
            host_json_path=host,
        )


def test_no_warning_when_no_otel_and_no_host_json(clean_root: logging.Logger) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_otel_logging_misconfig(host_json_path=None)


def test_6c_silent_for_non_otel_telemetry_mode(
    clean_root: logging.Logger,
    tmp_path: Path,
) -> None:
    host = tmp_path / "host.json"
    _write_host_json(host, {"telemetryMode": "ApplicationInsights"})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warn_otel_logging_misconfig(host_json_path=host)
