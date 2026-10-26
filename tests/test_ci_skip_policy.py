"""Lanes that certify a release or detect upstream drift must not pass by skipping."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _lane(workflow: str, command: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Return the one step that runs ``command`` and its effective env (workflow < job < step)."""
    wf = yaml.safe_load((WORKFLOWS / workflow).read_text())
    found = [
        (step, {**wf.get("env", {}), **job.get("env", {}), **step.get("env", {})})
        for job in wf["jobs"].values()
        for step in job.get("steps", [])
        if command in step.get("run", "")
    ]
    assert len(found) == 1, f"{workflow}: expected exactly one step running {command!r}"
    return found[0]


@pytest.mark.parametrize(
    ("workflow", "command"), [("e2e-azure.yml", "-m e2e"), ("otel-nightly.yml", "pytest")]
)
def test_lane_forbids_skips_and_cannot_swallow_a_failure(workflow: str, command: str) -> None:
    step, env = _lane(workflow, command)
    assert str(env.get("FAIL_ON_SKIP")) == "1"
    assert "|| true" not in step["run"]
    assert not step.get("continue-on-error")


def test_azure_certification_wires_app_insights() -> None:
    _, env = _lane("e2e-azure.yml", "-m e2e")
    assert env.get("APPINSIGHTS_NAME")
    assert env.get("E2E_RESOURCE_GROUP")


def test_missing_app_insights_fails_certification_without_network() -> None:
    env = {
        **os.environ,
        "FAIL_ON_SKIP": "1",
        "APPINSIGHTS_NAME": "",
        "E2E_BASE_URL": "http://127.0.0.1:1",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--no-cov",
            "-m",
            "e2e",
            "tests/e2e/test_logging_e2e.py::test_structured_log_appears_in_app_insights",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "APPINSIGHTS_NAME not set" in result.stdout
    assert "FAIL_ON_SKIP=1" in result.stdout


def test_missing_upstream_module_fails_canary_instead_of_passing_skip() -> None:
    script = """
import importlib.abc
import sys
import pytest

class MissingModule(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'opentelemetry.sdk._logs':
            raise ModuleNotFoundError('simulated removed upstream module', name=fullname)

sys.meta_path.insert(0, MissingModule())
sys.exit(pytest.main(['--no-cov', 'tests/test_otel_contract.py']))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "FAIL_ON_SKIP": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "simulated removed upstream module" in result.stdout
