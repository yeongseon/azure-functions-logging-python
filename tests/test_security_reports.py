import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.security_reports import summarize


def test_semgrep_summary_omits_source_and_sensitive_metadata(tmp_path: Path) -> None:
    scope = tmp_path / "scope"
    scope.mkdir()
    source = scope / "app.py"
    source.write_text("x = 1\n")
    report = {
        "paths": {"scanned": [str(source)]},
        "errors": [],
        "results": [{"extra": {"lines": "password=SYNTHETIC_SECRET", "severity": "ERROR"}}],
    }
    summary = summarize("semgrep", report, [scope], 1)
    assert summary["result"] == "findings"
    assert summary["findings"] == 1
    assert "SYNTHETIC_SECRET" not in json.dumps(summary)
    assert str(tmp_path) not in json.dumps(summary)


@pytest.mark.parametrize("mutation", ["empty", "missing", "error", "bad-status", "malformed"])
def test_semgrep_report_cannot_pass_incomplete_scan(tmp_path: Path, mutation: str) -> None:
    scope = tmp_path / "scope"
    scope.mkdir()
    source = scope / "app.py"
    source.write_text("x = 1\n")
    report: dict[str, Any] = {"paths": {"scanned": [str(source)]}, "errors": [], "results": []}
    status = 0
    if mutation == "empty":
        report["paths"] = {"scanned": []}
    elif mutation == "missing":
        (scope / "missing.py").write_text("y = 2\n")
    elif mutation == "error":
        report["errors"] = [{"message": "token=SYNTHETIC_SECRET"}]
    elif mutation == "bad-status":
        status = 2
    else:
        report = {}
    summary = summarize("semgrep", report, [scope], status)
    assert summary["result"] == "tool-error"
    assert "SYNTHETIC_SECRET" not in json.dumps(summary)


def test_clean_semgrep_report_passes_only_complete_scope(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("x = 1\n")
    summary = summarize(
        "semgrep",
        {"paths": {"scanned": [str(source)]}, "results": [], "errors": []},
        [tmp_path],
        0,
    )
    assert summary["result"] == "success"
    assert summary["scanned_files"] == 1


def test_bandit_summary_drops_code_and_preserves_findings_count(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("x = 1\n")
    report = {
        "metrics": {str(source): {"loc": 1}, "_totals": {"loc": 1}},
        "results": [{"code": "password=SYNTHETIC_SECRET"}],
        "errors": [],
    }
    summary = summarize("bandit", report, [tmp_path], 1)
    assert summary["result"] == "findings"
    assert "SYNTHETIC_SECRET" not in json.dumps(summary)


def test_required_scanner_evidence_runs_and_uploads_after_failure() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/security.yml").read_text())
    steps = workflow["jobs"]["semgrep"]["steps"]
    scan = next(step for step in steps if step.get("run") == "make security-semgrep")
    upload = next(
        step for step in steps if step.get("with", {}).get("path") == "test-results/semgrep.json"
    )
    assert scan["if"] == upload["if"] == "always()"
    assert not scan.get("continue-on-error")
    assert any("semgrep/semgrep-action@713efdd" in step.get("uses", "") for step in steps)


def test_bandit_zero_loc_keeps_parse_error_count(tmp_path: Path) -> None:
    summary = summarize(
        "bandit",
        {"metrics": {"_totals": {"loc": 0}}, "results": [], "errors": [{"reason": "secret"}]},
        [tmp_path],
        0,
    )
    assert summary["result"] == "tool-error"
    assert summary["errors"] == 1


def test_bandit_counts_targeted_and_blanket_suppressions(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("x = 1\n")
    summary = summarize(
        "bandit",
        {
            "metrics": {str(source): {}, "_totals": {"loc": 1, "nosec": 2, "skipped_tests": 24}},
            "results": [],
            "errors": [],
        },
        [tmp_path],
        0,
    )
    assert summary["suppressions"] == 26
