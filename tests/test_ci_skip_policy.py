"""Lanes that certify a release or detect upstream drift must not pass by skipping."""

from __future__ import annotations

from pathlib import Path
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
