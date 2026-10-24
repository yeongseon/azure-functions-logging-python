from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

from tools import dependency_audit_policy, security_evidence
from tools.security_report import Check, Status


def test_bandit_inventory_matches_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a complete fake scan; When inventory loses a file; Then coverage fails closed.
    metrics = {
        p.as_posix(): {"loc": 1}
        for surface in security_evidence.SCOPE
        for p in Path(surface).rglob("*.py")
    }
    metrics["_totals"] = {"loc": len(metrics)}
    raw = json.dumps({"errors": [], "metrics": metrics, "results": []})

    def complete(command: list[str], **kwargs: str) -> subprocess.CompletedProcess[str]:
        assert "--ignore-nosec" in command
        return subprocess.CompletedProcess(command, 0, stdout=raw, stderr="CANARY_SECRET")

    monkeypatch.setattr(subprocess, "run", complete)
    monkeypatch.setattr(security_evidence, "version", lambda name: "1.9.4")
    assert security_evidence.run_bandit().status == Status.PASS
    del metrics[next(iter(metrics))]
    raw = json.dumps({"errors": [], "metrics": metrics, "results": []})
    assert security_evidence.run_bandit().status == Status.INCOMPLETE


@pytest.mark.parametrize("marker", ["# nosec", "# nosec B999", "# nosec B110"])
def test_unlisted_suppression_is_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, marker: str
) -> None:
    # Given a new inline marker; When scanned; Then its exact location needs review.
    (tmp_path / "src").mkdir()
    (tmp_path / "src/x.py").write_text(f"value = 1 {marker}\n")
    (tmp_path / "security").mkdir()
    (tmp_path / "security/bandit-policy.json").write_text(
        '{"schema_version":1,"exceptions":[],"inline_suppressions":[]}'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(security_evidence, "SCOPE", ("src",))
    raw = json.dumps(
        {
            "errors": [],
            "metrics": {"_totals": {"loc": 40}, **{f"src/{i}.py": {} for i in range(40)}},
            "results": [],
        }
    )

    def complete(*args: str, **kwargs: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=raw, stderr="")

    monkeypatch.setattr(subprocess, "run", complete)
    monkeypatch.setattr(security_evidence, "version", lambda name: "1.9.4")
    assert security_evidence.run_bandit().status == Status.INCOMPLETE


@pytest.mark.parametrize("failure", [OSError(), subprocess.TimeoutExpired("scanner", 1)])
def test_execution_errors_never_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: OSError | subprocess.TimeoutExpired
) -> None:
    # Given unavailable tools; When invoked; Then no raw diagnostic is retained.
    (tmp_path / "example.dist-info").mkdir()

    def fail(*args: str, **kwargs: str) -> subprocess.CompletedProcess[str]:
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    assert security_evidence.run_bandit().status == Status.TOOL_ERROR
    assert dependency_audit_policy.run_audit(tmp_path, tmp_path).status == Status.INCOMPLETE


def test_audit_uses_only_candidate_installation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given an isolated inventory; When audited; Then tooling cannot contaminate its closure.
    (tmp_path / "example.dist-info").mkdir()
    (tmp_path / "example.dist-info/METADATA").write_text("Name: example\nVersion: 1\n")
    (tmp_path / "candidate.dist-info").mkdir()
    (tmp_path / "candidate.dist-info/METADATA").write_text("Name: candidate\nVersion: 99\n")
    wheel = tmp_path / "candidate.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("candidate.dist-info/METADATA", "Name: candidate\nVersion: 99\n")
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema_version":1,"blocking":"all-known-runtime","exceptions":[]}')

    def complete(command: list[str], **kwargs: str) -> subprocess.CompletedProcess[str]:
        assert Path(command[command.index("--requirement") + 1]).read_text() == "example==1\n"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"dependencies":[{"name":"example","version":"1","vulns":[]}]}',
            stderr="CANARY_SECRET",
        )

    monkeypatch.setattr(subprocess, "run", complete)
    monkeypatch.setattr(dependency_audit_policy, "version", lambda name: "2.10.1")
    assert dependency_audit_policy.run_audit(tmp_path, policy, wheel).status == Status.PASS


@pytest.mark.parametrize("development", [False, True])
@pytest.mark.parametrize(
    "status,code", [(Status.FAIL, 1), (Status.TOOL_ERROR, 2), (Status.INCOMPLETE, 3)]
)
def test_audit_cli_preserves_failure_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, development: bool, status: Status, code: int
) -> None:
    # Given a classified failure; When CLI writes evidence; Then the same failure reaches CI.
    args = [
        "audit",
        "--site-packages",
        str(tmp_path),
        "--output",
        str(tmp_path),
        "--candidate-wheel",
        "candidate.whl",
    ]
    if development:
        args.append("--development")
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(
        dependency_audit_policy,
        "run_audit",
        lambda path, policy, wheel: Check("pip-audit", (), status, 1),
    )
    assert dependency_audit_policy.main() == code
    assert json.loads((tmp_path / "summary.json").read_text())["checks"][0]["status"] == status


def test_real_cli_writes_stdlib_only_evidence(tmp_path: Path) -> None:
    # Given the real CLI; When action evidence is missing; Then it writes INCOMPLETE and exits 3.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.security_evidence",
            "semgrep",
            "--outcome",
            "cancelled",
            "--output",
            str(tmp_path),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 3
    assert json.loads((tmp_path / "summary.json").read_text())["schema_version"] == 1


def test_incomplete_scan_cannot_be_excepted() -> None:
    # Given missing coverage; When exceptions are applied; Then they cannot waive completeness.
    check = Check("bandit", (), Status.INCOMPLETE, 0)
    assert security_evidence.apply_bandit_policy(check, "{}", date(2026, 10, 22)) == check
