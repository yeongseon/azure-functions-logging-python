from __future__ import annotations

from datetime import date
import json

import pytest

from tools.dependency_audit_policy import classify_audit
from tools.security_exceptions import parse_exceptions
from tools.security_report import EvidenceError, Status, load

TODAY = date(2026, 10, 22)
POLICY = '{"schema_version":1,"blocking":"all-known-runtime","exceptions":[]}'


def payload(vulnerable: bool = False) -> str:
    return json.dumps(
        {
            "dependencies": [
                {
                    "name": "example",
                    "version": "1",
                    "vulns": [
                        {"id": "CVE-2026-12345", "fix_versions": [], "description": "CANARY_SECRET"}
                    ]
                    if vulnerable
                    else [],
                }
            ]
        }
    )


@pytest.mark.parametrize("vulnerable,expected", [(False, Status.PASS), (True, Status.FAIL)])
def test_any_known_runtime_advisory_blocks(vulnerable: bool, expected: Status) -> None:
    # Given resolved packages; When audited; Then even UNKNOWN severity blocks.
    result = classify_audit(payload(vulnerable), int(vulnerable), policy_raw=POLICY, today=TODAY)
    assert result.status == expected
    assert "CANARY_SECRET" not in repr(result)


@pytest.mark.parametrize("raw", ["", "invalid", "{}", '{"dependencies":[]}'])
def test_invalid_or_zero_package_audit_is_tool_error(raw: str) -> None:
    # Given unusable audit output; When classified; Then it is never a clean scan.
    assert classify_audit(raw, 0, policy_raw=POLICY, today=TODAY).status == Status.TOOL_ERROR


def test_skipped_package_is_incomplete() -> None:
    # Given a package the tool skipped; When classified; Then coverage is incomplete.
    raw = '{"dependencies":[{"name":"x","version":"1","skip_reason":"CANARY_SECRET"}]}'
    assert classify_audit(raw, 0, policy_raw=POLICY, today=TODAY).status == Status.INCOMPLETE


@pytest.mark.parametrize(
    "expires,expected", [("2026-10-21", Status.FAIL), ("2026-11-21", Status.PASS)]
)
def test_exception_expiry_and_affectedness(expires: str, expected: Status) -> None:
    # Given an owned exception; When evaluated; Then only current/no-fix exceptions apply.
    policy = json.loads(POLICY)
    policy["exceptions"] = [
        {
            "id": "CVE-2026-12345",
            "package": "example",
            "kind": "fix-not-available",
            "reason": "no patched release",
            "owner": "maintainer",
            "added": "2026-10-01",
            "expires": expires,
        }
    ]
    result = classify_audit(payload(True), 1, policy_raw=json.dumps(policy), today=TODAY)
    assert result.status == expected
    assert bool(result.exceptions_applied) == (expected == Status.PASS)
    raw = json.loads(payload(True))
    raw["dependencies"][0]["vulns"][0]["fix_versions"] = ["2"]
    assert (
        classify_audit(json.dumps(raw), 1, policy_raw=json.dumps(policy), today=TODAY).status
        == Status.FAIL
    )


def test_stale_exception_is_reported() -> None:
    # Given a current unused exception; When evaluated; Then it is visible for removal.
    policy = json.loads(POLICY)
    policy["exceptions"] = [
        {
            "id": "CVE-2026-12345",
            "package": "example",
            "kind": "not-affected",
            "reason": "reviewed unreachable path",
            "owner": "maintainer",
            "added": "2026-10-01",
            "expires": "2026-11-01",
        }
    ]
    result = classify_audit(payload(), 0, policy_raw=json.dumps(policy), today=TODAY)
    assert result.status == Status.PASS
    assert result.counts["stale_exceptions"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"expires": "2027-10-22"},
        {"added": "2026-11-01"},
        {"kind": "ignore-all"},
        {"line": -1},
        {"line": True},
        {"owner": ""},
        {"reason": ""},
    ],
)
def test_invalid_exception_policy_fails(patch: dict[str, str | int]) -> None:
    # Given malformed policy; When parsed; Then no exception can hide a finding.
    rule = {
        "id": "CVE-1",
        "package": "example",
        "kind": "not-affected",
        "reason": "reviewed",
        "owner": "maintainer",
        "added": "2026-10-01",
        "expires": "2026-11-01",
        **patch,
    }
    with pytest.raises((EvidenceError, ValueError)):
        parse_exceptions(load(json.dumps({"exceptions": [rule]}))["exceptions"], TODAY)


@pytest.mark.parametrize("code", [0, 2])
def test_inconsistent_exit_status_fails(code: int) -> None:
    # Given findings inconsistent with exit status; When classified; Then tooling failed.
    assert (
        classify_audit(payload(True), code, policy_raw=POLICY, today=TODAY).status
        == Status.TOOL_ERROR
    )
