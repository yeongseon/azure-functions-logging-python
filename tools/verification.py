"""Canonical verification CLI, shared by Make and CI's selected interpreter."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

from tools.verification_environment import clean, doctor
from tools.verification_evidence import Status, Summary, collect, publish, report, save
from tools.verification_host import host_smoke
from tools.verification_process import run

OTEL_TESTS = (
    "tests/test_otel.py",
    "tests/test_otel_contract.py",
    "tests/test_otel_filters.py",
    "tests/test_host_config_otel.py",
)


def pytest_command(lane: str, extra: list[str]) -> list[str]:
    directory = Path("test-results") / lane
    command = [sys.executable, "-m", "pytest"]
    match lane:
        case "test":
            command += [
                "tests/",
                "-m",
                "not e2e",
                "--ignore=tests/e2e",
                "--ignore=tests/host_smoke",
                "--cov-report=xml:" + str(directory / "coverage.xml"),
            ]
        case "otel":
            command += [*OTEL_TESTS, "--no-cov"]
        case _:
            command += ["tests/e2e/", "-m", "e2e", "--no-cov"]
    return command + ["--junitxml=" + str(directory / "junit.xml"), *extra]


def execute(lane: str, extra: list[str]) -> int:
    directory = Path("test-results") / lane
    if directory.exists():
        shutil.rmtree(directory)
    (directory / "logs").mkdir(parents=True)
    command = pytest_command(lane, extra)
    reason, code, blocked = "", 0, False
    try:
        if lane in {"azure-e2e", "local-e2e"}:
            required = ["E2E_BASE_URL", "E2E_EXPECTED_VERSION"]
            if lane == "azure-e2e":
                required += ["APPINSIGHTS_NAME", "E2E_RESOURCE_GROUP"]
            missing = [key for key in required if not os.environ.get(key, "").strip()]
            if lane == "azure-e2e" and shutil.which("az") is None:
                missing.append("az")
            if missing:
                blocked, code, reason = True, 2, "Missing prerequisites: " + ", ".join(missing)
        if lane in {"host-smoke", "host-matrix"}:
            command = ["func", "start", "(managed logging host smoke)"]
            if doctor(quality=False):
                blocked, code, reason = True, 2, "Missing required integration tools"
            else:
                code = host_smoke(directory, matrix=lane == "host-matrix")
        elif not blocked:
            code = run(command, directory / "logs/runner.log")
    except KeyboardInterrupt:
        code, reason = 130, "Interrupted; owned child processes terminated"
    except (OSError, ET.ParseError, ValueError) as error:
        code, reason = 2, str(error)
    try:
        summary = collect(directory, command, code)
    except (ET.ParseError, ValueError) as error:
        summary = Summary(
            1,
            lane,
            tuple(command),
            0,
            0,
            0,
            0,
            "INCOMPLETE",
            2,
            reason=f"Invalid evidence: {error}",
        )
    if blocked:
        summary = replace(summary, status="INCOMPLETE")
        ET.ElementTree(ET.Element("testsuite", name=lane, tests="0")).write(
            directory / "junit.xml", encoding="unicode"
        )
    summary = save(directory, replace(summary, reason=reason or summary.reason))
    publish(summary)
    return summary.exit_code


def aggregate(lane: str, outcomes: list[Summary]) -> int:
    status: Status = "FAIL" if any(item.status == "FAIL" for item in outcomes) else "PASS"
    if status == "PASS" and (not outcomes or any(item.status != "PASS" for item in outcomes)):
        status = "INCOMPLETE"
    directory = Path("test-results") / lane
    directory.mkdir(parents=True, exist_ok=True)
    summary = Summary(
        1,
        lane,
        ("make", lane),
        sum(s.selected for s in outcomes),
        sum(s.passed for s in outcomes),
        sum(s.failed for s in outcomes),
        sum(s.skipped for s in outcomes),
        status,
        int(status != "PASS"),
        reason="; ".join(f"{item.lane}={item.status}" for item in outcomes),
        otel_instrumentation=next(
            (
                s.otel_instrumentation
                for s in outcomes
                if s.otel_instrumentation != "NOT_APPLICABLE"
            ),
            "NOT_APPLICABLE",
        ),
    )
    (directory / "lanes.json").write_text(json.dumps([asdict(s) for s in outcomes], indent=2))
    publish(save(directory, summary))
    return summary.exit_code


def integration() -> int:
    directory = Path("test-results/integration")
    if directory.exists():
        shutil.rmtree(directory)
    outcomes = []
    for lane in ("otel", "host-smoke", "host-matrix"):
        execute(lane, [])
        source = Path("test-results") / lane
        outcomes.append(Summary(**json.loads((source / "summary.json").read_text())))
        for pattern, destination in (("**/*junit.xml", "junit"), ("logs/*", "logs")):
            for artifact in source.glob(pattern):
                target = directory / destination / f"{lane}-{artifact.name}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(artifact, target)
    return aggregate("integration", outcomes)


def verify() -> int:
    directory = Path("test-results/verify")
    if directory.exists():
        shutil.rmtree(directory)
    outcomes = []
    for target in ("check", "test", "integration", "wheel-smoke", "docs"):
        path = Path("test-results") / target / "summary.json"
        path.unlink(missing_ok=True)
        code = run(["make", target], directory / "logs" / f"{target}.log", 1200)
        if path.exists():
            summary = Summary(**json.loads(path.read_text()))
            if code and summary.status == "PASS":
                summary = replace(summary, status="FAIL", exit_code=code)
        else:
            required = target != "check"
            summary = Summary(
                1,
                target,
                ("make", target),
                int(not required),
                int(not required and code == 0),
                int(code != 0),
                0,
                "INCOMPLETE" if required else ("FAIL" if code else "PASS"),
                code or int(required),
                reason="Required lane summary missing" if required else "",
            )
        outcomes.append(summary)
    return aggregate("verify", outcomes)


def focused(lane: str, command: list[str]) -> int:
    directory = Path("test-results") / lane
    if directory.exists():
        shutil.rmtree(directory)
    code = run(command, directory / "logs/runner.log", 1200)
    summary = Summary(
        1,
        lane,
        tuple(command),
        1,
        int(code == 0),
        int(code != 0),
        0,
        "PASS" if code == 0 else "FAIL",
        code,
    )
    publish(save(directory, summary))
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "lane",
        choices=(
            "test",
            "integration",
            "otel",
            "host-smoke",
            "host-matrix",
            "verify",
            "azure-e2e",
            "local-e2e",
            "report",
            "doctor",
            "clean",
            "focused",
        ),
    )
    args, extra = parser.parse_known_args()
    if not (3, 11) <= sys.version_info[:2] < (3, 15):
        parser.error("Python >=3.11,<3.15 is required")
    match args.lane:
        case "report":
            return report(Path("test-results"))
        case "doctor":
            return doctor()
        case "clean":
            clean(Path.cwd())
            return 0
        case "verify":
            return verify()
        case "integration":
            return integration()
        case "focused":
            return focused(extra[0], [sys.executable, *extra[1:]])
        case _:
            return execute(args.lane, extra)


if __name__ == "__main__":
    raise SystemExit(main())
