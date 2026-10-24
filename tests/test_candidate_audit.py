from __future__ import annotations

import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

import pytest

from tools.dependency_audit_policy import run_audit
from tools.security_evidence import semgrep_evidence
from tools.security_report import Status


@pytest.mark.parametrize("mode", ["clean", "advisory", "skip", "mismatch", "missing"])
def test_unpublished_candidate_audits_exact_third_party_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    wheel = tmp_path / "candidate.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            "candidate.dist-info/METADATA", "Name: azure-functions-logging\nVersion: 99.0\n"
        )
    for name, version in [
        ("azure-functions-logging", "98.0" if mode == "mismatch" else "99.0"),
        ("dependency", "1.0"),
    ]:
        dist = tmp_path / f"{name.replace('-', '_')}-{version}.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n")
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema_version":1,"blocking":"all-known-runtime","exceptions":[]}')

    def audit(command: list[str], **kwargs: str) -> subprocess.CompletedProcess[str]:
        requirements = Path(command[command.index("--requirement") + 1]).read_text()
        assert requirements == "dependency==1.0\n"
        assert "--no-deps" in command and "--disable-pip" in command
        item: dict[str, object] = {"name": "dependency", "version": "1.0", "vulns": []}
        if mode == "skip":
            item = {"name": "dependency", "skip_reason": "not on PyPI"}
        if mode == "advisory":
            item["vulns"] = [{"id": "CVE-2026-12345", "fix_versions": []}]
        return subprocess.CompletedProcess(
            command,
            int(mode == "advisory"),
            json.dumps({"dependencies": [] if mode == "missing" else [item]}),
            "",
        )

    monkeypatch.setattr(subprocess, "run", audit)
    monkeypatch.setattr("tools.dependency_audit_policy.version", lambda _: "2.10.1")
    result = run_audit(tmp_path, policy, wheel)
    assert (
        result.status
        == {
            "clean": Status.PASS,
            "advisory": Status.FAIL,
            "skip": Status.INCOMPLETE,
            "mismatch": Status.INCOMPLETE,
            "missing": Status.TOOL_ERROR,
        }[mode]
    )


def test_semgrep_action_success_is_incomplete() -> None:
    assert semgrep_evidence("success").status == Status.INCOMPLETE
