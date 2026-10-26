"""Fail unless Bandit analysed every Python file in the declared scope and found nothing.

Bandit exits 0 for an empty directory, a missing path and files it cannot parse (it only
lists them as skipped), so its exit status alone can pass vacuously.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


def problems(report: dict[str, Any], scopes: list[str]) -> list[str]:
    scanned = {Path(name).as_posix() for name in report["metrics"]}
    found: list[str] = []
    if report["metrics"]["_totals"]["loc"] == 0:
        found.append("no code was analysed")
    found += [f"skipped {e['filename']}: {e['reason']}" for e in report["errors"]]
    found += [
        f"not scanned: {path.as_posix()}"
        for scope in scopes
        for path in sorted(Path(scope).rglob("*.py"))
        if path.as_posix() not in scanned
    ]
    found += [
        f"{r['filename']}:{r['line_number']} {r['test_id']} {r['issue_text']}"
        for r in report["results"]
    ]
    return found


def main(report: str, scopes: list[str]) -> int:
    data = json.loads(Path(report).read_text(encoding="utf-8"))
    found = problems(data, scopes)
    for message in found:
        print(f"bandit: {message}", file=sys.stderr)
    if not found:
        print(f"bandit: {data['metrics']['_totals']['loc']} lines analysed, no findings")
    return 1 if found else 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python tools/check_bandit_report.py <report.json> <scope>...")
    raise SystemExit(main(sys.argv[1], sys.argv[2:]))
