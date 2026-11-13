"""Offline reproduction of the documented host.json conflict warning and its safe fixes.

Uses synthetic ``tests/data/host_json/*.json`` fixtures through the public
``setup_logging(host_json_path=...)`` path in Azure/Core Tools mode. No Azure
resources are involved, and the library only *warns*: it never edits host.json or
overrides host-level filters.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import logging
import os
from pathlib import Path
import re
import warnings

import pytest

from azure_functions_logging import setup_logging
import azure_functions_logging._setup as setup_mod

_ROOT = Path(__file__).resolve().parent.parent
_FIXTURES = _ROOT / "tests" / "data" / "host_json"
_DOC = _ROOT / "docs" / "troubleshooting.md"
_DOCUMENTED_WARNING = (
    "host configuration logLevel for default is set to 'Warning' which is more "
    "restrictive than the configured level 'INFO'. Logs below 'Warning' will be "
    "suppressed by the Azure Functions host."
)


@pytest.fixture(autouse=True)
def _isolated_azure_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run setup_logging in Core Tools mode with a clean environment and root logger."""
    for name in list(os.environ):
        if name.startswith("AzureFunctionsJobHost__"):
            monkeypatch.delenv(name)
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)
    monkeypatch.delenv("PYTHON_ENABLE_OPENTELEMETRY", raising=False)
    monkeypatch.delenv("PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY", raising=False)
    monkeypatch.setenv("FUNCTIONS_WORKER_RUNTIME", "python")
    root = logging.getLogger()
    saved = (list(root.handlers), list(root.filters), root.level)
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()
    yield
    root.handlers[:] = saved[0]
    root.filters[:] = saved[1]
    root.setLevel(saved[2])
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()


def _setup_and_collect(host_json: Path) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        setup_logging(level=logging.INFO, host_json_path=host_json)
    return [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


def test_restrictive_default_emits_the_documented_warning_once() -> None:
    messages = _setup_and_collect(_FIXTURES / "conflicting.json")
    assert messages == [_DOCUMENTED_WARNING]


def test_warning_does_not_edit_host_json_or_change_levels_or_handlers() -> None:
    fixture = _FIXTURES / "conflicting.json"
    before = fixture.read_bytes()
    root = logging.getLogger()
    root.setLevel(logging.ERROR)
    handlers_before = list(root.handlers)

    _setup_and_collect(fixture)

    assert fixture.read_bytes() == before  # no automatic correction
    assert root.level == logging.ERROR  # host-managed level untouched
    assert root.handlers == handlers_before  # no handler added


def test_corrected_host_json_is_silent() -> None:
    assert _setup_and_collect(_FIXTURES / "corrected.json") == []


def test_function_override_keeps_the_strict_default_warning() -> None:
    messages = _setup_and_collect(_FIXTURES / "function_override.json")
    assert messages == [_DOCUMENTED_WARNING]
    assert not any("OrdersHttp" in message for message in messages)


def test_app_setting_override_silences_the_warning_without_editing_host_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AzureFunctionsJobHost__logging__logLevel__default", "Information")
    assert _setup_and_collect(_FIXTURES / "conflicting.json") == []


def test_troubleshooting_fixtures_match_the_files_and_make_no_override_claim() -> None:
    text = _DOC.read_text(encoding="utf-8")
    blocks = dict(
        re.findall(
            r"<!-- host-json-fixture: (\S+) -->\s*```json\n(.*?)```",
            text,
            re.S,
        )
    )
    assert set(blocks) == {"conflicting.json", "corrected.json"}
    for name, body in blocks.items():
        fixture = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
        assert json.loads(body) == fixture, name
    assert _DOCUMENTED_WARNING in text
    assert "does not edit `host.json`" in text
    assert "does not override" in text
