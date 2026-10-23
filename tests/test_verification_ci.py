from __future__ import annotations

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_ci_canonical_runners_preserve_matrix_and_failure_uploads() -> None:
    workflows = ROOT / ".github/workflows"
    ci = (workflows / "ci-test.yml").read_text()
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in ci
    assert 'python-version: ["3.11", "3.12"]' in ci
    assert "python -m tools.verification test --no-cov" in ci
    assert "python -m tools.verification integration" in ci
    assert "python -m tools.verification otel" in ci
    assert "make install-ci" in ci
    for name in (
        "ci-test.yml",
        "e2e-azure.yml",
        "publish-pypi.yml",
        "otel-nightly.yml",
        "e2e-host-matrix.yml",
    ):
        text = (workflows / name).read_text()
        evidence = [
            block for block in text.split("      - name:") if "path: test-results/**" in block
        ]
        assert evidence, name
        assert all("if: always()" in block for block in evidence)
    assert 'core_tools: ["4", "4.12.0"]' in (workflows / "e2e-host-matrix.yml").read_text()


def test_ci_selects_actual_interpreter_without_hatch() -> None:
    result = subprocess.run(
        ["make", "--no-print-directory", "-n", "test", "CI=true", "PYTHON=matrix-python"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "matrix-python -m tools.verification test"


def test_check_all_exact_alias_and_deep_clean_preserved() -> None:
    assert "check-all: verify\n\n" in (ROOT / "Makefile").read_text()
    result = subprocess.run(["make", "-n", "clean-all"], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0
    assert "-m tools.verification clean" in result.stdout
    assert "__pycache__" in result.stdout
    assert "rm -rf .DS_Store .venv" in result.stdout


def test_release_requires_cloud_monitor_and_candidate_version() -> None:
    text = (ROOT / ".github/workflows/e2e-azure.yml").read_text()
    assert "python -m tools.verification azure-e2e" in text
    for field in (
        "E2E_BASE_URL:",
        "E2E_EXPECTED_VERSION:",
        "APPINSIGHTS_NAME:",
        "E2E_RESOURCE_GROUP:",
    ):
        assert field in text
    assert text.index("tools.verification azure-e2e") < text.index("- name: Record certification")
