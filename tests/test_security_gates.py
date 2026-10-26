"""The Bandit gate must fail instead of passing vacuously (real Bandit, tiny scratch trees)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import security_reports

SHELL_TRUE = "import subprocess\nsubprocess.call('echo', shell=True)\n"
TWO_FILES = {"a.py": "x = 1\n", "gone.py": "y = 2\n"}


def _gate(tmp_path: Path, files: dict[str, str] | None, *bandit_args: str) -> int:
    """Run Bandit as ``make security`` does, then the guard; ``None`` leaves the scope missing."""
    scope = tmp_path / "scope"
    if files is not None:
        scope.mkdir()
        for name, text in files.items():
            (scope / name).write_text(text)
    report = tmp_path / "bandit.json"
    bandit = [sys.executable, "-m", "bandit", "-r", str(scope), "-q", "-f", "json", "-o"]
    run = subprocess.run([*bandit, str(report), *bandit_args], check=False, capture_output=True)
    output = tmp_path / "summary.json"
    code = security_reports.main("bandit", str(report), str(output), run.returncode, [str(scope)])
    summary = json.loads(output.read_text())
    assert summary["exit_status"] == run.returncode
    assert "code" not in summary and "results" not in summary
    if code == 0:
        assert summary["result"] == "success"
    else:
        assert summary["result"] in {"findings", "tool-error"}
    return code


@pytest.mark.parametrize(
    ("files", "bandit_args", "exit_code"),
    [
        pytest.param({"ok.py": "x = 1\n"}, (), 0, id="clean-tree"),
        # Bandit 1.9.4 draws a progress bar on stdout above 50 files; the report must still parse.
        pytest.param({f"m{n}.py": "x = 1\n" for n in range(60)}, (), 0, id="over-50-files"),
        pytest.param({}, (), 1, id="empty-dir"),
        pytest.param({"empty.py": ""}, (), 1, id="only-empty-files"),
        pytest.param(None, (), 1, id="missing-dir"),
        pytest.param({"bad.py": "def (:\n"}, (), 1, id="unparsable-file"),
        pytest.param(TWO_FILES, ("-x", "gone.py"), 1, id="narrowed"),
        pytest.param({"bad.py": SHELL_TRUE}, (), 1, id="new-shell-true-finding"),
    ],
)
def test_bandit_gate_exit_code(
    tmp_path: Path, files: dict[str, str] | None, bandit_args: tuple[str, ...], exit_code: int
) -> None:
    assert _gate(tmp_path, files, *bandit_args) == exit_code
