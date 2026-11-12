"""docs/ci-inventory.md must match .github/workflows and the required checks."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = _ROOT / ".github" / "workflows"
_DOC = _ROOT / "docs" / "ci-inventory.md"


def _doc() -> str:
    return _DOC.read_text(encoding="utf-8")


def _documented_files() -> set[str]:
    block = _doc().split("<!-- workflow-inventory:start -->", 1)[1]
    block = block.split("<!-- workflow-inventory:end -->", 1)[0]
    return set(re.findall(r"^\| `([a-z0-9-]+\.yml)` \|", block, re.M))


def _required_contexts() -> list[str]:
    match = re.search(r"<!-- required-checks:(.*?) -->", _doc())
    assert match, "required-checks marker missing from docs/ci-inventory.md"
    return [part.strip() for part in match.group(1).split(",")]


def _triggers(workflow: dict[Any, Any]) -> set[str]:
    on = workflow.get(True, workflow.get("on"))
    return set(on) if isinstance(on, dict) else set(on or [])


def test_inventory_lists_exactly_the_workflow_files() -> None:
    actual = {p.name for p in _WORKFLOWS.glob("*.yml")}
    documented = _documented_files()
    assert actual == documented, (
        f"docs/ci-inventory.md drifted: undocumented={sorted(actual - documented)}, "
        f"documented but missing={sorted(documented - actual)}"
    )


@pytest.mark.parametrize("context", _required_contexts())
def test_required_context_is_reported_by_a_pull_request_workflow(context: str) -> None:
    reporters = []
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not _triggers(data) & {"pull_request", "pull_request_target"}:
            continue
        for job_id, job in data["jobs"].items():
            if context in {job_id, str(job.get("name", job_id))}:
                reporters.append(f"{path.name}:{job_id}")
    assert reporters, f"no pull_request workflow job reports required check {context!r}"


def test_ci_required_depends_on_every_ci_test_gate_job() -> None:
    data = yaml.safe_load((_WORKFLOWS / "ci-test.yml").read_text(encoding="utf-8"))
    gate_jobs = set(data["jobs"]) - {"ci-required"}
    assert gate_jobs == set(data["jobs"]["ci-required"]["needs"])


def test_removed_duplicate_workflows_stay_removed_and_coverage_remains() -> None:
    assert not (_WORKFLOWS / "docs.yml").exists()
    assert not (_WORKFLOWS / "mermaid-lint.yml").exists()
    ci = (_WORKFLOWS / "ci-test.yml").read_text(encoding="utf-8")
    assert "mkdocs build --strict" in ci
    assert "scripts/render_mermaid.py" in ci
    assert "tools/lint_doc_links.py" in ci
