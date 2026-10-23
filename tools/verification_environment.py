"""Read-only prerequisites and allowlisted generated-artifact cleanup."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


def doctor(live: bool = True, quality: bool = True) -> int:
    healthy = (3, 11) <= sys.version_info[:2] < (3, 15)
    modules_available = True
    print(f"python REQUIRED >=3.11,<3.15: {sys.version.split()[0]} ({sys.executable})")
    for module in ("venv", "ruff", "mypy", "pytest", "bandit", "build", "mkdocs"):
        found = importlib.util.find_spec(module) is not None
        print(f"{module} REQUIRED: {'found' if found else 'MISSING'}")
        healthy = healthy and found
        modules_available = modules_available and found
    if not modules_available:
        print("development environment not created: run make install")
    for tool in ("func", "azurite"):
        path = shutil.which(tool)
        print(f"{tool} REQUIRED for integration/verify: {path or 'MISSING'}")
        if live:
            healthy = healthy and path is not None
    if quality:
        mermaid = shutil.which("mmdc")
        print(f"mmdc REQUIRED for check/verify: {mermaid or 'MISSING'}")
        healthy = healthy and mermaid is not None
    return 0 if healthy else 1


def clean(root: Path) -> None:
    for name in (
        "test-results",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".coverage",
        "coverage.xml",
        "htmlcov",
        "site",
        "__pycache__",
    ):
        path = root / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    for tree in ("src", "tests", "tools", "scripts", "examples", "benchmarks"):
        for path in (root / tree).rglob("__pycache__"):
            if not any(part in {".venv", "venv", "env"} for part in path.parts):
                if path.is_symlink():
                    path.unlink()
                else:
                    shutil.rmtree(path)
