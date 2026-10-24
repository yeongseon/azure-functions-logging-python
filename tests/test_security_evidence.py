from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from tools.security_evidence import apply_bandit_policy, classify_bandit, semgrep_evidence
from tools.security_report import Check, Status, write_report


def payload() -> str:
    return json.dumps(
        {
            "errors": [],
            "metrics": {"_totals": {"loc": 10}, "src/x.py": {"loc": 10}},
            "results": [],
        }
    )


@pytest.mark.parametrize(
    "raw,code,status",
    [
        ("", 2, Status.TOOL_ERROR),
        ("invalid", 0, Status.TOOL_ERROR),
        ('{"errors":[],"metrics":{"_totals":{}},"results":[]}', 0, Status.INCOMPLETE),
    ],
)
def test_missing_evidence_fails_closed(raw: str, code: int, status: Status) -> None:
    # Given missing evidence; When classified; Then it cannot pass.
    assert classify_bandit(raw, code, floor=1).status == status


def test_complete_scan_has_real_counts() -> None:
    # Given one scanned file; When classified; Then its inventory is reported.
    result = classify_bandit(payload(), 0, floor=1)
    assert result.status == Status.PASS
    assert result.counts == {"files": 1, "loc": 10, "errors": 0}


@pytest.mark.parametrize("severity", ["LOW", "MEDIUM", "HIGH"])
def test_findings_block_without_raw_diagnostics(severity: str, tmp_path: Path) -> None:
    # Given secret-bearing diagnostics; When rendered; Then only metadata survives.
    data = json.loads(payload())
    data["results"] = [
        {
            "test_id": "B105",
            "filename": "src/x.py",
            "line_number": 3,
            "issue_severity": severity,
            "issue_confidence": "HIGH",
            "code": "Authorization: Bearer CANARY_SECRET",
            "issue_text": "AccountKey=CANARY_SECRET",
        }
    ]
    result = classify_bandit(json.dumps(data), 1, floor=1)
    summary = tmp_path / "summary.md"
    assert write_report([result], tmp_path, summary) == 1
    saved = (tmp_path / "summary.json").read_text()
    assert "CANARY_SECRET" not in saved + summary.read_text()
    assert result.counts[f"severity.{severity}"] == 1
    parsed = json.loads(saved)
    assert parsed["schema_version"] == 1
    assert set(parsed["checks"][0]) == {
        "name",
        "scope",
        "status",
        "exit_status",
        "counts",
        "suppressions",
        "exceptions_applied",
        "tool_versions",
        "findings",
        "message",
    }


@pytest.mark.parametrize("code", [0, 2])
def test_error_files_are_tool_errors(code: int) -> None:
    # Given a scanner error; When classified; Then it is not a vulnerability result.
    data = json.loads(payload())
    data["errors"] = [{"reason": "CANARY_SECRET"}]
    assert classify_bandit(json.dumps(data), code, floor=1).status == Status.TOOL_ERROR


@pytest.mark.parametrize("field", ["nosec", "skipped_tests"])
def test_suppression_overflow_is_incomplete(field: str) -> None:
    # Given an unexpected scanner skip; When classified; Then completeness fails.
    data = json.loads(payload())
    data["metrics"]["_totals"][field] = 1
    assert classify_bandit(json.dumps(data), 0, floor=1).status == Status.INCOMPLETE


def test_static_policy_matches_exact_location_and_expires() -> None:
    # Given an exact reviewed exception; When evaluated; Then expiry/location matter.
    data = json.loads(payload())
    data["results"] = [
        {
            "test_id": "B404",
            "filename": "src/x.py",
            "line_number": 1,
            "issue_severity": "LOW",
            "issue_confidence": "HIGH",
        }
    ]
    check = classify_bandit(json.dumps(data), 1, floor=1)
    rule = {
        "id": "B404",
        "file": "src/x.py",
        "line": 1,
        "kind": "reviewed-static",
        "reason": "fixed shell-free command",
        "owner": "maintainer",
        "added": "2026-10-01",
        "expires": "2026-11-01",
    }
    policy = json.dumps({"schema_version": 1, "exceptions": [rule]})
    applied = apply_bandit_policy(check, policy, date(2026, 10, 22))
    assert applied.status == Status.PASS
    assert applied.exceptions_applied == ("B404:src/x.py:1",)
    assert apply_bandit_policy(check, policy, date(2026, 11, 2)).status == Status.FAIL
    rule["line"] = 2
    stale = apply_bandit_policy(
        check, json.dumps({"schema_version": 1, "exceptions": [rule]}), date(2026, 10, 22)
    )
    assert stale.status == Status.FAIL
    assert stale.counts["stale_exceptions"] == 1
    assert apply_bandit_policy(check, "invalid", date(2026, 10, 22)).status == Status.TOOL_ERROR


@pytest.mark.parametrize(
    "outcome,status",
    [
        ("success", Status.INCOMPLETE),
        ("failure", Status.TOOL_ERROR),
        ("skipped", Status.INCOMPLETE),
    ],
)
def test_semgrep_outcome_is_not_a_vulnerability(outcome: str, status: Status) -> None:
    # Given action outcome only; When recorded; Then finding counts stay unknown.
    assert semgrep_evidence(outcome).status == status


@pytest.mark.parametrize(
    "status,code",
    [(Status.PASS, 0), (Status.FAIL, 1), (Status.TOOL_ERROR, 2), (Status.INCOMPLETE, 3)],
)
def test_status_exit_codes_are_distinct(status: Status, code: int) -> None:
    # Given a status; When returned to CI; Then its code is unambiguous.
    assert Check("test", (), status, 0).returncode == code
