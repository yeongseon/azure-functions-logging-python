"""Deployment results must not expose secret-bearing infrastructure outputs."""

from pathlib import Path
import shlex

import yaml


def test_azure_deployment_suppresses_secret_bearing_result() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/e2e-azure.yml").read_text())
    steps = workflow["jobs"]["deploy_and_test"]["steps"]
    deployment = next(
        step for step in steps if step.get("name") == "Deploy infra with App Insights (Bicep)"
    )

    arguments = shlex.split(deployment["run"].replace("\\\n", ""))

    assert arguments[arguments.index("--output") + 1] == "none"
    assert "--debug" not in arguments
