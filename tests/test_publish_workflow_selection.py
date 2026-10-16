from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def test_cookbook_runtime_selection_is_explicit_and_logging_specific() -> None:
    workflow = WORKFLOW.read_text()

    assert 'pytest -v -m "e2e and package_logging"' in workflow
    assert "tests/e2e/test_package_runtime.py --no-cov" in workflow
    assert "hatch run e2e tests/e2e/test_http_examples.py" not in workflow


def test_cookbook_checkout_and_failure_evidence_are_reproducible() -> None:
    workflow = WORKFLOW.read_text()

    assert "COOKBOOK_REF: 3b78ff2373d4f4dd5e8209c3324c4df245ed4665" in workflow
    assert "sha256sum candidate-dist/*.whl" in workflow
    assert "Verify logging-specific collection" in workflow
    assert "Upload sanitized host diagnostics" in workflow


def test_collection_guard_skips_coverage_and_rejects_zero_collection() -> None:
    import re

    workflow = WORKFLOW.read_text()
    pattern = r"^[1-9][0-9]*(/[0-9]+)? tests? collected"

    assert "--collect-only --no-cov" in workflow
    assert f'grep -Eq "{pattern}"' in workflow
    assert re.search(pattern, "1/3 tests collected (2 deselected) in 0.04s", re.MULTILINE)
    assert re.search(pattern, "3 tests collected in 0.04s", re.MULTILINE)
    assert not re.search(pattern, "0/3 tests collected (3 deselected) in 0.04s", re.MULTILINE)
    assert not re.search(pattern, "no tests collected in 0.04s", re.MULTILINE)


def test_host_smoke_command_arguments_are_exact() -> None:
    import shlex

    import yaml

    workflow = yaml.safe_load(WORKFLOW.read_text())
    steps = workflow["jobs"]["cookbook-host-smoke"]["steps"]
    command = next(
        step["run"] for step in steps if step.get("name", "").startswith("Boot cookbook func host")
    )
    arguments = shlex.split(command.replace("\\\n", " "), posix=True)

    assert "tests/e2e/test_package_runtime.py" in arguments
    assert "--junitxml=pytest-results.xml" in arguments
