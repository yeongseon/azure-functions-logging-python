"""Allowlisted scanner evidence: never copy source, payloads or diagnostic text."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Literal, TypedDict


class ScanSummary(TypedDict):
    scanner: str
    result: Literal["success", "findings", "tool-error"]
    exit_status: int
    expected_files: int
    scanned_files: int
    findings: int
    errors: int
    suppressions: int


def summarize(scanner: str, report: dict[str, Any], scopes: list[Path], status: int) -> ScanSummary:
    expected = {p.resolve() for scope in scopes for p in scope.rglob("*.py")}
    summary: ScanSummary = {
        "scanner": scanner,
        "result": "tool-error",
        "exit_status": status,
        "expected_files": len(expected),
        "scanned_files": 0,
        "findings": 0,
        "errors": 0,
        "suppressions": 0,
    }
    try:
        results, errors = report["results"], report["errors"]
        if not isinstance(results, list) or not isinstance(errors, list):
            return summary
        summary["findings"] = len(results)
        summary["errors"] = len(errors)
        if scanner == "semgrep":
            paths = report["paths"]["scanned"]
        elif scanner == "bandit":
            metrics = report["metrics"]
            summary["suppressions"] = int(metrics["_totals"].get("nosec", 0)) + int(
                metrics["_totals"].get("skipped_tests", 0)
            )
            if metrics["_totals"]["loc"] <= 0:
                return summary
            paths = [name for name in metrics if name != "_totals"]
        else:
            return summary
        scanned = {Path(name).resolve() for name in paths}
        summary["scanned_files"] = len(scanned)
        summary["findings"] = len(results)
        summary["errors"] = len(errors)
        if (
            not scopes
            or any(not scope.is_dir() for scope in scopes)
            or not expected
            or not expected <= scanned
            or errors
            or status not in {0, 1}
        ):
            return summary
        if status == 1 and not results:
            return summary
        summary["result"] = "findings" if results else "success"
    except (KeyError, TypeError, ValueError):
        return summary
    return summary


def main(scanner: str, raw: str, output: str, status: int, scopes: list[str]) -> int:
    try:
        report = json.loads(Path(raw).read_text())
        if not isinstance(report, dict):
            report = {}
    except (OSError, ValueError):
        report = {}
    summary = summarize(scanner, report, [Path(scope) for scope in scopes], status)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, sort_keys=True) + "\n")
    message = (
        f"{scanner}: {summary['result']}; {summary['scanned_files']}/"
        f"{summary['expected_files']} files; {summary['findings']} findings; "
        f"{summary['errors']} errors; {summary['suppressions']} suppressions; exit {status}\n"
    )
    print(message, end="")
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a") as stream:
            stream.write(message)
    return 0 if summary["result"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5:]))
