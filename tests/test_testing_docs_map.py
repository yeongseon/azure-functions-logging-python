"""Every file path named in docs/testing.md must exist (stops the test map drifting)."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "docs" / "testing.md"
_PATH = re.compile(
    r"`((?:tests|benchmarks|tools|examples|infra|\.github/workflows)/[A-Za-z0-9_./-]+"
    r"\.(?:py|yml|bicep))`"
)


def _documented_paths() -> list[str]:
    return sorted(set(_PATH.findall(_DOC.read_text(encoding="utf-8"))))


def test_testing_doc_names_paths() -> None:
    assert len(_documented_paths()) >= 40


@pytest.mark.parametrize("rel", _documented_paths())
def test_documented_path_exists(rel: str) -> None:
    assert (_ROOT / rel).is_file(), f"docs/testing.md names a missing file: {rel}"


def test_documented_commands_exist_in_makefile_and_pytest_config() -> None:
    makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    doc = _DOC.read_text(encoding="utf-8")
    for target in ("test", "e2e-local", "e2e-azure", "bench"):
        assert f"make {target}" in doc
        assert re.search(rf"^{re.escape(target)}:", makefile, re.M), target
    assert "e2e: real Azure end-to-end tests" in pyproject
    assert "-m 'not e2e'" in pyproject
