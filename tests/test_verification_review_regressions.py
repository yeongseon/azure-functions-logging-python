from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from tools.verification_evidence import Summary, redact, save
from tools.verification_host import wait_ready


@pytest.mark.parametrize(
    "text",
    [
        '{"Authorization": "Bearer CANARY"}',
        "{'Proxy-Authorization': 'Basic CANARY'}",
        '{"password": "alpha CANARY beta"}',
        '{"token": "with \\"escaped\\" CANARY"}',
        "SharedAccessKey=CANARY;SharedAccessKeyName=Root",
        "InstrumentationKey=CANARY;IngestionEndpoint=https://CANARY/;",
        '<failure message="Authorization: Bearer CANARY">x</failure>',
    ],
)
def test_quoted_credentials_are_consumed_whole(text: str) -> None:
    assert "CANARY" not in redact(text)


def test_save_preserves_structure_binary_and_external_symlink(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\xff\xfe"
    (tmp_path / "chart.png").write_bytes(png)
    outside = tmp_path.parent / (tmp_path.name + "-outside.log")
    outside.write_text("password=CANARY")
    (tmp_path / "link.log").symlink_to(outside)
    (tmp_path / "extra.json").write_text('{"password": 123, "ok": true}')
    save(tmp_path, Summary(1, "test", ('Authorization: "Bearer CANARY"',), 1, 1, 0, 0, "PASS", 0))
    assert "CANARY" not in (tmp_path / "summary.json").read_text()
    assert json.loads((tmp_path / "extra.json").read_text())["ok"]
    assert (tmp_path / "chart.png").read_bytes() == png
    assert outside.read_text() == "password=CANARY"


def test_known_secret_replaced_before_patterns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_API_TOKEN", 'pre;fix&CANARY "quoted" value')
    assert "CANARY" not in redact(json.dumps({"x": 'pre;fix&CANARY "quoted" value'}))


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError(), OSError()])
def test_readiness_retries_transient_failure(
    error: OSError, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = Mock()
    process.poll.return_value = None
    request = Mock(side_effect=[error, nullcontext(Mock(status=200))])
    monkeypatch.setattr("tools.verification_host.urlopen", request)
    monkeypatch.setattr("tools.verification_host.time.sleep", lambda _: None)
    wait_ready(process, "http://localhost/health")
    assert request.call_count == 2


def test_check_failure_retains_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.verification import focused

    monkeypatch.chdir(tmp_path)
    assert focused("check", [sys.executable, "-c", "print('password=CANARY'); exit(7)"]) == 7
    summary = json.loads(Path("test-results/check/summary.json").read_text())
    assert (summary["status"], summary["exit_code"]) == ("FAIL", 7)
    assert "CANARY" not in Path("test-results/check/logs/runner.log").read_text()


def test_check_wraps_prerequisites_in_evidence() -> None:
    result = subprocess.run(["make", "-n", "check", "CI=true"], capture_output=True, text=True)
    assert "tools.verification focused check" in result.stdout
    assert "tools.verification_check" in result.stdout
