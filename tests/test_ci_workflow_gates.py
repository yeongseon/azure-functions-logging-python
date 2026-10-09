from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci-test.yml"


def gate_source() -> str:
    workflow = WORKFLOW.read_text()
    match = re.search(
        r"python3 - <<'EVAL'\n(?P<body>.*?)\n\s+EVAL",
        workflow,
        flags=re.DOTALL,
    )
    assert match is not None
    lines = match.group("body").splitlines()
    indentation = min(len(line) - len(line.lstrip()) for line in lines if line.strip())
    return "\n".join(line[indentation:] for line in lines)


def classifier_source() -> str:
    workflow = WORKFLOW.read_text()
    match = re.search(
        r"      - name: Classify changed files.*?        run: \|\n"
        r"(?P<body>.*?)\n\n  # Lint",
        workflow,
        flags=re.DOTALL,
    )
    assert match is not None
    return textwrap.dedent(match.group("body"))


def evaluate_gate(
    *,
    full_required: str,
    docs_changed: str,
    results: dict[str, dict[str, str]],
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "FULL_REQUIRED": full_required,
        "DOCS_CHANGED": docs_changed,
        "RESULTS": json.dumps(results),
    }
    return subprocess.run(
        ["python3", "-c", gate_source()],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def expected_results(*, full: bool, docs: bool) -> dict[str, dict[str, str]]:
    full_result = "success" if full else "skipped"
    results = {
        job: {"result": full_result}
        for job in (
            "quality",
            "test",
            "minimum-dependencies",
            "artifact-build",
            "artifact-python310-negative",
            "artifact-python311",
            "host-smoke",
        )
    }
    results["changes"] = {"result": "success"}
    results["docs-check"] = {"result": "success" if docs else "skipped"}
    return results


@pytest.mark.parametrize(
    ("full_required", "docs_changed"),
    [("", "true"), ("invalid", "true"), ("true", ""), ("true", "invalid")],
)
def test_gate_rejects_missing_or_invalid_classifier_outputs(
    full_required: str, docs_changed: str
) -> None:
    results = expected_results(full=True, docs=True)

    completed = evaluate_gate(
        full_required=full_required,
        docs_changed=docs_changed,
        results=results,
    )

    assert completed.returncode != 0


def test_gate_rejects_classifier_success_without_required_work() -> None:
    results = expected_results(full=False, docs=False)

    completed = evaluate_gate(full_required="false", docs_changed="false", results=results)

    assert completed.returncode != 0


@pytest.mark.parametrize("result", ["failure", "skipped", "cancelled"])
def test_gate_requires_changes_job_success(result: str) -> None:
    results = expected_results(full=True, docs=False)
    results["changes"] = {"result": result}

    completed = evaluate_gate(full_required="true", docs_changed="false", results=results)

    assert completed.returncode != 0


@pytest.mark.parametrize("result", ["failure", "skipped"])
def test_gate_rejects_unclassified_needs_job(result: str) -> None:
    results = expected_results(full=True, docs=False)
    results["new-required-job"] = {"result": result}

    completed = evaluate_gate(full_required="true", docs_changed="false", results=results)

    assert completed.returncode != 0


def test_gate_accepts_successful_unclassified_needs_job() -> None:
    results = expected_results(full=True, docs=False)
    results["new-required-job"] = {"result": "success"}

    completed = evaluate_gate(full_required="true", docs_changed="false", results=results)

    assert completed.returncode == 0, completed.stderr


def test_fork_pull_request_runs_trusted_classifier() -> None:
    workflow = WORKFLOW.read_text()

    assert "github.event.pull_request.base.sha" in workflow
    assert "github.event.pull_request.head.repo.full_name != github.repository" in workflow
    assert 'tools/ci_classify_changes.sh < "$changed_files"' in workflow


def test_push_range_requires_before_to_be_ancestor() -> None:
    workflow = WORKFLOW.read_text()

    assert 'git merge-base --is-ancestor "$BEFORE_SHA" "$SHA"' in workflow


def test_force_push_range_fails_safe_in_synthetic_repository(tmp_path: Path) -> None:
    env = os.environ | {
        "GIT_MASTER": "1",
        "GIT_AUTHOR_NAME": "CI test",
        "GIT_AUTHOR_EMAIL": "ci@example.invalid",
        "GIT_COMMITTER_NAME": "CI test",
        "GIT_COMMITTER_EMAIL": "ci@example.invalid",
    }
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ci_classify_changes.sh").write_text(
        (ROOT / "tools" / "ci_classify_changes.sh").read_text()
    )
    (tmp_path / "README.md").write_text("base\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, env=env, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (tmp_path / "README.md").write_text("old history\n")
    subprocess.run(["git", "commit", "-qam", "old"], cwd=tmp_path, env=env, check=True)
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "--detach", base], cwd=tmp_path, env=env, check=True)
    (tmp_path / "README.md").write_text("force-pushed history\n")
    subprocess.run(["git", "commit", "-qam", "replacement"], cwd=tmp_path, env=env, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    output = tmp_path / "github-output"
    run_env = env | {
        "EVENT_NAME": "push",
        "BASE_SHA": "",
        "HEAD_SHA": "",
        "PR_NUMBER": "",
        "BEFORE_SHA": before,
        "SHA": sha,
        "GITHUB_OUTPUT": str(output),
    }

    subprocess.run(
        ["bash", "-c", classifier_source()],
        cwd=tmp_path,
        env=run_env,
        check=True,
    )

    assert output.read_text().splitlines() == [
        "docs_only=false",
        "docs_changed=true",
        "full_required=true",
    ]
