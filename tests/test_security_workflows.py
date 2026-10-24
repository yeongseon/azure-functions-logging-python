from pathlib import Path
import tomllib

import yaml

from tools.lint_release_workflows import check_pins, check_publish_needs
from tools.security_evidence import SCOPE

ROOT = Path(__file__).resolve().parents[1]


def test_release_gate_preserves_existing_tiers_and_candidate() -> None:
    # Given release configuration; When inspected; Then the audit adds to every existing gate.
    text = (ROOT / ".github/workflows/publish-pypi.yml").read_text()
    jobs = yaml.safe_load(text)["jobs"]
    assert check_publish_needs(text, "publish-pypi.yml") == []
    assert set(jobs["publish"]["needs"]) == {
        "build",
        "lib-tests",
        "cookbook-smoke",
        "cookbook-host-smoke",
        "azure-e2e",
        "runtime-dependency-audit",
    }
    gate = jobs["runtime-dependency-audit"]
    assert gate["permissions"] == {"contents": "read"}
    assert gate["needs"] == "build"
    assert gate["strategy"]["matrix"]["interpreter"] == ["3.11", "3.12", "3.13", "3.14"]
    assert gate["strategy"]["matrix"]["closure"] == ["base", "otel"]
    assert not gate.get("continue-on-error")
    assert all(not s.get("continue-on-error") for s in gate["steps"])
    download = next(s for s in gate["steps"] if "download-artifact@" in s.get("uses", ""))
    assert download["with"]["name"] == "dist"
    commands = "\n".join(s.get("run", "") for s in gate["steps"])
    assert "pip-audit==2.10.1" in commands
    assert "--without-pip" in commands
    assert '"${wheels[0]}[otel]"' in commands
    assert "make security-runtime" in commands
    assert "--candidate-wheel" in commands
    assert "build --wheel" not in commands


def test_evidence_uploads_always_run_with_canonical_pins() -> None:
    # Given every evidence workflow; When inspected; Then failed scans retain redacted evidence.
    for filename in ("security.yml", "dependency-audit.yml", "publish-pypi.yml"):
        text = (ROOT / ".github/workflows" / filename).read_text()
        workflow = yaml.safe_load(text)
        assert workflow["permissions"] == {"contents": "read"}
        assert check_pins(text, filename) == []
        uploads = [
            s
            for job in workflow["jobs"].values()
            for s in job.get("steps", [])
            if "upload-artifact@" in s.get("uses", "")
            and s.get("with", {}).get("path", "").startswith("security-results")
        ]
        assert uploads
        assert all(
            s["if"] == "always()" and s["with"]["if-no-files-found"] == "error" for s in uploads
        )


def test_security_scans_declared_executable_surfaces() -> None:
    # Given declared surfaces; When workflow runs; Then neither source nor examples are omitted.
    workflow = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())
    assert SCOPE == ("src", "examples", "scripts", "tools", "benchmarks")
    steps = workflow["jobs"]["bandit"]["steps"]
    assert any(
        s.get("if") == "always()" and "make security-bandit" in s.get("run", "") for s in steps
    )
    assert any("security-typecheck" in s.get("run", "") for s in steps)
    semgrep = workflow["jobs"]["semgrep"]["steps"]
    action = next(s for s in semgrep if "semgrep/semgrep-action@" in s.get("uses", ""))
    assert action["uses"] == "semgrep/semgrep-action@713efdd345f3035192eaa63f56867b88e63e4e5d"
    assert action["with"]["config"] == "p/python"
    assert not action.get("continue-on-error")
    assert any(
        s.get("if") == "always()" and "make security-semgrep" in s.get("run", "") for s in semgrep
    )
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["envs"][
        "default"
    ]["scripts"]
    assert "--strict" in scripts["security-typecheck"]


def test_scheduled_audits_reuse_policy_as_reporting_only() -> None:
    # Given scheduled audit lanes; When inspected; Then runtime/OTel/dev use one classifier.
    workflow = yaml.safe_load((ROOT / ".github/workflows/dependency-audit.yml").read_text())
    steps = workflow["jobs"]["pip-audit"]["steps"]
    audits = [s for s in steps if "make security-runtime-report" in s.get("run", "")]
    assert len(audits) == 3
    assert all(s["continue-on-error"] for s in audits)
    assert any("--development" in s["run"] for s in audits)
