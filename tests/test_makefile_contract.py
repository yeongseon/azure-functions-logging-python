"""Make must not reinstall tooling per target, type-check twice or hide a missing tool (#614).

``make`` runs on a copy of the Makefile with ``PATH`` limited to stubs that log their arguments, so
nothing is installed and no network is used; ``make -n`` runs no recipe at all.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
HATCH = "venv/bin/hatch"
TOOLS = {"venv/bin/pip", HATCH, "bin/python3", "bin/git", "bin/func", "bin/azurite"}
CASES = [  # target, stubs missing, exit 0, stub calls, output
    ("bootstrap", (), True, "", ""),
    ("bootstrap", (HATCH,), True, "install hatch\n", "Installing Hatch"),
    ("doctor", ("bin/func", "bin/azurite"), True, "", "missing  func (optional"),
    ("doctor", (HATCH,), False, "", "MISSING  "),
    ("doctor", ("bin/python3",), False, "", "MISSING  python3"),
    ("doctor", ("bin/git",), False, "", "MISSING  git"),
]


def _make(tmp: Path, *args: str, missing: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    shutil.copy(ROOT / "Makefile", tmp / "Makefile")
    (tmp / "log").touch()
    for tool in TOOLS - set(missing):
        (tmp / tool).parent.mkdir(parents=True, exist_ok=True)
        (tmp / tool).write_text('#!/bin/sh\necho "$*" >> "$STUB_LOG"\n')
        (tmp / tool).chmod(0o755)
    env = {"PATH": str(tmp / "bin"), "STUB_LOG": str(tmp / "log")}
    cmd = [shutil.which("make") or "make", f"VENV_DIR={tmp / 'venv'}", *args]
    return subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True)


@pytest.mark.parametrize(("target", "missing", "ok", "calls", "output"), CASES)
def test_bootstrap_and_doctor(
    tmp_path: Path, target: str, missing: tuple[str, ...], ok: bool, calls: str, output: str
) -> None:
    done = _make(tmp_path, target, missing=missing)
    assert (done.returncode == 0) is ok
    assert output in done.stdout
    assert (tmp_path / "log").read_text() == calls  # pip only for a missing Hatch; doctor: none


def test_a_directory_at_the_hatch_path_is_not_hatch(tmp_path: Path) -> None:
    (tmp_path / HATCH).mkdir(parents=True)
    assert _make(tmp_path, "doctor", missing=(HATCH,)).returncode != 0
    assert _make(tmp_path, "bootstrap", missing=(HATCH,)).returncode == 0
    assert (tmp_path / "log").read_text() == "install hatch\n"


def test_check_type_checks_once_and_never_upgrades_pip(tmp_path: Path) -> None:
    dry = _make(tmp_path, "-n", "check").stdout
    assert dry.count("hatch run lint") == 1 and "typecheck" not in dry
    assert _make(tmp_path, "check").returncode == 0
    assert (tmp_path / "log").read_text() == "run lint\n"  # one Hatch call, no pip call
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["envs"]
    assert scripts["default"]["scripts"]["lint"].count("hatch run typecheck") == 1
    assert "--upgrade" not in (ROOT / "Makefile").read_text()
