from __future__ import annotations

from importlib.machinery import ModuleSpec
import json
from pathlib import Path
import sys

import pytest

from tools.verification import execute, integration, pytest_command, verify
from tools.verification_environment import clean, doctor
from tools.verification_evidence import (
    APP_INSIGHTS_TEST,
    VERSION_TEST,
    Summary,
    collect,
    publish,
    redact,
    report,
    save,
)
from tools.verification_process import child, run
from tools.verification_wheel import main as wheel_smoke


@pytest.mark.parametrize(
    ("cases", "code", "status"),
    [
        ("", 0, "INCOMPLETE"),
        ("", 5, "INCOMPLETE"),
        ("<testcase><skipped/></testcase>", 0, "INCOMPLETE"),
        ("<testcase/><testcase><skipped/></testcase>", 0, "INCOMPLETE"),
        ("<testcase><failure/></testcase>", 1, "FAIL"),
        ("<testcase/>", 0, "PASS"),
        ("<testcase/>", 124, "FAIL"),
    ],
)
def test_required_lane_classification(tmp_path: Path, cases: str, code: int, status: str) -> None:
    (tmp_path / "junit.xml").write_text(f"<testsuite>{cases}</testsuite>")
    summary = collect(tmp_path, ["pytest"], code)
    assert summary.status == status
    assert (summary.exit_code == 0) == (status == "PASS")


@pytest.mark.parametrize(
    ("lane", "status", "cloud_status"),
    [
        ("azure-e2e", "INCOMPLETE", "INCOMPLETE"),
        ("local-e2e", "PASS", "NOT_APPLICABLE"),
    ],
)
def test_skipped_app_insights_never_certifies_cloud(
    tmp_path: Path, lane: str, status: str, cloud_status: str
) -> None:
    directory = tmp_path / lane
    directory.mkdir()
    (directory / "junit.xml").write_text(
        f'<testsuite><testcase name="http"/><testcase name="{VERSION_TEST}"/>'
        f'<testcase name="{APP_INSIGHTS_TEST}"><skipped/></testcase></testsuite>'
    )
    summary = collect(directory, ["pytest"], 0)
    assert summary.status == status
    assert summary.cloud_monitor == cloud_status
    assert summary.deployed_version_match == "PASS"
    assert summary.cloud_tests_not_run == (APP_INSIGHTS_TEST,)


def test_missing_required_cloud_assertion_is_incomplete(tmp_path: Path) -> None:
    directory = tmp_path / "azure-e2e"
    directory.mkdir()
    (directory / "junit.xml").write_text(
        f'<testsuite><testcase name="{VERSION_TEST}"/></testsuite>'
    )
    assert collect(directory, ["pytest"], 0).status == "INCOMPLETE"


def test_cloud_certificate_requires_both_observed_assertions(tmp_path: Path) -> None:
    directory = tmp_path / "azure-e2e"
    directory.mkdir()
    (directory / "junit.xml").write_text(
        f'<testsuite><testcase name="{VERSION_TEST}"/>'
        f'<testcase name="{APP_INSIGHTS_TEST}"/></testsuite>'
    )
    summary = collect(directory, ["pytest"], 0)
    assert (summary.status, summary.cloud_monitor, summary.deployed_version_match) == (
        "PASS",
        "PASS",
        "PASS",
    )
    assert summary.cloud_tests_not_run == ()


@pytest.mark.parametrize(
    "secret",
    [
        "AccountKey=VERYSECRET;",
        "SharedAccessSignature=VERYSECRET;",
        "code=VERYSECRET&x=1",
        "x-functions-key: VERYSECRET",
        "Authorization: Bearer VERYSECRET",
        "password=VERYSECRET",
        "token=VERYSECRET",
        "AzureWebJobsStorage=VERYSECRET",
        "sas=VERYSECRET",
        "api_key=VERYSECRET",
        "DefaultEndpointsProtocol=https;AccountName=PRIVATE;AccountKey=VERYSECRET;",
        "InstrumentationKey=VERYSECRET;IngestionEndpoint=https://VERYSECRET/;",
        '"connection_string": "VERYSECRET"',
    ],
)
def test_canaries_removed_from_junit_logs_console_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], secret: str
) -> None:
    (tmp_path / "junit.xml").write_text(
        "<testsuite><testcase><system-out>"
        + secret.replace("&", "&amp;")
        + "</system-out></testcase></testsuite>"
    )
    (tmp_path / "runner.log").write_text(secret)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "job-summary"))
    summary = save(tmp_path, collect(tmp_path, ["pytest", secret], 0))
    publish(summary)
    assert "VERYSECRET" not in capsys.readouterr().out
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "VERYSECRET" not in path.read_text()
    json.loads((tmp_path / "summary.json").read_text())


def test_environment_secret_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOM_ACCESS_TOKEN", "opaque-sensitive-value")
    assert redact("diagnostic opaque-sensitive-value") == "diagnostic [REDACTED]"


def test_saved_report_does_not_execute_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "test"
    directory.mkdir()
    (directory / "junit.xml").write_text("<testsuite><testcase/></testsuite>")
    (directory / "coverage.xml").write_text('<coverage line-rate="0.99"/>')
    save(directory, collect(directory, ["not-an-executable"], 0))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "job-summary"))
    assert report(tmp_path) == 0
    data = json.loads((directory / "summary.json").read_text())
    assert data["schema_version"] == 1
    assert (data["selected"], data["passed"], data["failed"], data["skipped"]) == (1, 1, 0, 0)
    assert data["coverage"] == 0.99
    assert str(directory / "junit.xml") in data["supporting_files"]
    assert "passed=1" in (tmp_path / "job-summary").read_text()


def test_empty_report_is_read_only(tmp_path: Path) -> None:
    assert report(tmp_path) == 1
    assert list(tmp_path.iterdir()) == []


def test_missing_tools_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tools.verification_environment.shutil.which", lambda _: None)
    assert doctor() != 0
    assert execute("host-smoke", []) != 0
    assert (
        json.loads(Path("test-results/host-smoke/summary.json").read_text())["status"]
        == "INCOMPLETE"
    )


def test_host_prerequisites_do_not_require_mermaid(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given all required Python modules and host tools, but no Mermaid executable.
    monkeypatch.setattr(
        "tools.verification_environment.importlib.util.find_spec",
        lambda module: ModuleSpec(module, loader=None),
    )
    monkeypatch.setattr(
        "tools.verification_environment.shutil.which",
        lambda tool: None if tool == "mmdc" else "/tools/" + tool,
    )
    assert doctor(quality=False) == 0
    assert doctor() != 0


@pytest.mark.parametrize("missing", ["venv", "ruff", "mypy", "pytest", "bandit", "build", "mkdocs"])
def test_host_prerequisites_fail_when_required_module_is_missing(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    # Given exactly one missing module, with every executable available.
    monkeypatch.setattr(
        "tools.verification_environment.importlib.util.find_spec",
        lambda module: None if module == missing else ModuleSpec(module, loader=None),
    )
    monkeypatch.setattr(
        "tools.verification_environment.shutil.which", lambda tool: "/tools/" + tool
    )

    # When checking host prerequisites, then the missing module must fail closed.
    assert doctor(quality=False) == 1


def test_offline_selection_keeps_all_privacy_tests() -> None:
    command = pytest_command("test", [])
    assert "tests/" in command
    assert "not e2e" in command
    assert [arg for arg in command if arg.startswith("--ignore")] == [
        "--ignore=tests/e2e",
        "--ignore=tests/host_smoke",
    ]
    assert "tests/test_otel_contract.py" in pytest_command("otel", [])


def test_clean_preserves_environments_storage_and_source(tmp_path: Path) -> None:
    for name in (".venv", "src", "shared-azurite", "test-results", "dist", "build"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "keep").touch()
    clean(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [".venv", "shared-azurite", "src"]


def test_clean_does_not_follow_artifact_symlink(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared/keep").touch()
    (tmp_path / "test-results").symlink_to(tmp_path / "shared", target_is_directory=True)
    clean(tmp_path)
    assert (tmp_path / "shared/keep").exists()


def test_process_failure_preserved(tmp_path: Path) -> None:
    assert run([sys.executable, "-c", "raise SystemExit(7)"], tmp_path / "log") == 7
    assert run(["/nonexistent/verification-command"], tmp_path / "missing") == 127


def test_interrupt_reaps_owned_child(tmp_path: Path) -> None:
    with (
        pytest.raises(KeyboardInterrupt),
        child([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path / "log") as process,
    ):
        raise KeyboardInterrupt
    assert process.poll() is not None


def test_timeout_reaps_and_redacts(tmp_path: Path) -> None:
    code = run(
        [sys.executable, "-u", "-c", "import time; print('password=VERYSECRET'); time.sleep(30)"],
        tmp_path / "log",
        1,
    )
    assert code == 124
    assert "VERYSECRET" not in (tmp_path / "log").read_text()


def test_wheel_smoke_rejects_stale_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/stale.whl").write_bytes(b"stale")

    def empty_build(command: list[str], log: Path, timeout: float = 600) -> int:
        assert "--outdir" in command
        assert str(tmp_path / "dist") not in command
        return 0

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tools.verification_wheel.run", empty_build)
    assert wheel_smoke() != 0


def test_integration_retains_separate_required_lanes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_execute(lane: str, extra: list[str]) -> int:
        calls.append(lane)
        save(Path("test-results") / lane, Summary(1, lane, ("test",), 0, 0, 0, 0, "INCOMPLETE", 1))
        return 1

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tools.verification.execute", fake_execute)
    assert integration() != 0
    assert calls == ["otel", "host-smoke", "host-matrix"]
    assert (
        json.loads(Path("test-results/integration/summary.json").read_text())["status"]
        == "INCOMPLETE"
    )


def test_verify_continues_after_failure_and_rejects_stale_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_run(command: list[str], log: Path, timeout: float = 600) -> int:
        calls.append(command[1])
        return 1

    monkeypatch.chdir(tmp_path)
    save(Path("test-results/test"), Summary(1, "test", ("old",), 1, 1, 0, 0, "PASS", 0))
    monkeypatch.setattr("tools.verification.run", fake_run)
    assert verify() != 0
    assert calls == ["check", "test", "integration", "wheel-smoke", "docs"]
    assert (
        json.loads(Path("test-results/verify/lanes.json").read_text())[1]["status"] == "INCOMPLETE"
    )
