"""The release publishes only after the candidate's runtime closure passes the advisory gate."""

from __future__ import annotations

from pathlib import Path
import re
import tomllib
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _gate() -> tuple[dict[str, Any], dict[str, Any]]:
    jobs = yaml.safe_load((ROOT / ".github/workflows/publish-pypi.yml").read_text())["jobs"]
    return jobs["publish"], jobs["runtime-dependency-audit"]


def test_publish_needs_the_audit_and_no_step_can_swallow_its_failure() -> None:
    publish, gate = _gate()
    assert "runtime-dependency-audit" in publish["needs"]
    assert gate["needs"] == "build"
    assert gate["permissions"] == {"contents": "read"}
    assert not gate.get("continue-on-error")
    assert not any(
        s.get("continue-on-error") or "|| true" in s.get("run", "") for s in gate["steps"]
    )


def test_audit_scans_the_downloaded_wheel_and_cannot_pass_vacuously() -> None:
    _, gate = _gate()
    download = next(s for s in gate["steps"] if "download-artifact" in s.get("uses", ""))
    script = next(s["run"] for s in gate["steps"] if "pip_audit" in s.get("run", ""))
    commands = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    audit = next(line for line in commands if "pip_audit" in line).split()
    assert download["with"]["name"] == "dist"
    assert any("dist/*.whl" in line for line in commands)
    assert any(line.startswith("test -s req.txt") for line in commands)
    assert {"--strict", "--no-deps", "--disable-pip"} <= set(audit)


def test_audit_covers_base_and_otel_on_the_oldest_and_newest_supported_python() -> None:
    _, gate = _gate()
    classifiers = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["classifiers"]
    minors = sorted(
        (int(m[1]), int(m[2]))
        for c in classifiers
        if (m := re.fullmatch(r"Programming Language :: Python :: (\d+)\.(\d+)", c))
    )
    oldest, newest = (f"{major}.{minor}" for major, minor in (minors[0], minors[-1]))
    matrix = gate["strategy"]["matrix"]
    assert matrix["extras"] == ["", "[otel]"]
    assert {oldest, newest} <= set(matrix["python"])
