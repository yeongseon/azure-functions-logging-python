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
