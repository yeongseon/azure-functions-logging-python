"""The secure-redaction troubleshooting recipe in docs/troubleshooting.md must stay true."""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
import io
import logging
from pathlib import Path
import re

import pytest

import azure_functions_logging._secure as secure_mod

_DOC = Path(__file__).resolve().parents[1] / "docs" / "troubleshooting.md"
_BLOCK = re.compile(
    r"<!-- secure-troubleshooting-repro:start -->\s*```python\n(?P<code>.*?)```\s*"
    r"<!-- secure-troubleshooting-repro:end -->",
    re.S,
)
_LOGGERS = ("troubleshooting.before", "troubleshooting.after", "troubleshooting.fixed")
_EXPECTED = {
    "handler present at preset time": True,
    "handler added after the preset": False,
    "attach_secure_redaction(handler)": True,
    "free text without a key/pattern": False,
}


@pytest.fixture(autouse=True)
def _restore_state() -> Iterator[None]:
    yield
    secure_mod.configure_secure_redaction(enabled=False)
    for name in _LOGGERS:
        logging.getLogger(name).handlers.clear()


def _run_recipe() -> dict[str, bool]:
    match = _BLOCK.search(_DOC.read_text(encoding="utf-8"))
    assert match, "repro block markers missing from docs/troubleshooting.md"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(match.group("code"), str(_DOC), "exec"), {"__name__": "recipe"})
    result: dict[str, bool] = {}
    for line in out.getvalue().splitlines():
        label, _, value = line.rpartition(":")
        result[label.strip()] = value.strip() == "True"
    return result


def test_recipe_reports_documented_protection_boundaries() -> None:
    assert _run_recipe() == _EXPECTED


def test_documented_expected_output_matches_recipe() -> None:
    text = _DOC.read_text(encoding="utf-8")
    for label, value in _EXPECTED.items():
        assert re.search(rf"^{re.escape(label)}\s*: {value}$", text, re.M), label


def test_recipe_uses_only_synthetic_canaries_and_no_blanket_guarantee() -> None:
    match = _BLOCK.search(_DOC.read_text(encoding="utf-8"))
    assert match
    assert "canary-token-0000" in match.group("code")
    assert "not a blanket no-PII guarantee" in _DOC.read_text(encoding="utf-8")
