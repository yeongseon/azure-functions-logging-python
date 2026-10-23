"""Public CLI contracts exercised through real subprocesses."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "target",
    [
        "install",
        "install-ci",
        "doctor",
        "format",
        "format-check",
        "check",
        "test",
        "integration",
        "verify",
        "e2e-azure",
        "report",
        "clean",
    ],
)
def test_routine_commands_do_not_bootstrap(target: str) -> None:
    # Given the public contract, when expanding a recipe without executing it.
    result = subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True)
    # Then setup is explicit, never a pip upgrade hidden in a routine command.
    assert result.returncode == 0, result.stderr
    assert "install --upgrade pip" not in result.stdout
    if target not in {"install", "install-ci"}:
        assert "pip install hatch" not in result.stdout


def test_check_is_complete_non_mutating_and_types_once() -> None:
    # Given the complete quality gate, when expanding its dependencies.
    result = subprocess.run(["make", "-n", "check-steps"], cwd=ROOT, capture_output=True, text=True)
    # Then every repository policy checker runs without mutation.
    assert result.returncode == 0
    assert result.stdout.count("-m mypy") == 1
    for name in (
        "lint_release_workflows.py",
        "lint_workflow_pins.py",
        "lint_hatch_matrix.py",
        "lint_doc_links.py",
    ):
        assert name in result.stdout
    assert "-m bandit" in result.stdout
    assert "scripts/render_mermaid.py" in result.stdout
    assert "--check" in result.stdout
    assert "--fix" not in result.stdout


def test_maintenance_uses_no_hatch_environment(tmp_path: Path) -> None:
    environment = dict(os.environ, HATCH_DATA_DIR=str(tmp_path / "hatch"), CI="")
    for target in ("doctor", "report"):
        subprocess.run(["make", target], cwd=ROOT, env=environment, capture_output=True, text=True)
    assert not list((tmp_path / "hatch").rglob("pyvenv.cfg"))


def test_unconfigured_azure_cli_fails_with_saved_incomplete(tmp_path: Path) -> None:
    # Given no Azure configuration and an isolated evidence directory.
    environment = dict(os.environ, PYTHONPATH=str(ROOT))
    environment.pop("E2E_BASE_URL", None)
    # When invoking the real canonical CLI, not a mocked execution function.
    result = subprocess.run(
        [sys.executable, "-m", "tools.verification", "azure-e2e"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    # Then absence of configuration is evidence, never successful certification.
    assert result.returncode != 0
    path = tmp_path / "test-results/azure-e2e/summary.json"
    assert path.exists(), result.stderr
    data = json.loads(path.read_text())
    assert data["status"] == "INCOMPLETE"
    assert data["selected"] == 0
