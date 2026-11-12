"""Docs and examples feature two context entry points and never leak bare tokens.

``logging_context`` and ``@with_context`` are the featured invocation-context entry
points; ``inject_context`` is a labelled low-level API that must be paired with
``restore_context`` wherever it is shown (#676).
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_EXCLUDED = {"CHANGELOG.md", "changelog.md", "release_history.md", "PRD.md"}
_FENCE = re.compile(r"```python\n(.*?)```", re.S)


def _sources() -> list[Path]:
    files = [_ROOT / "README.md", *sorted((_ROOT / "docs").glob("*.md"))]
    files += sorted((_ROOT / "examples").rglob("*.py"))
    return [f for f in files if f.name not in _EXCLUDED]


def _python_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [text] if path.suffix == ".py" else _FENCE.findall(text)


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_no_bare_inject_context_without_restore(path: Path) -> None:
    for block in _python_blocks(path):
        if re.search(r"\binject_context\(", block):
            assert "restore_context(" in block, (
                f"{path.relative_to(_ROOT)} shows inject_context() without restore_context()"
            )


def _first_python_block_after(text: str, heading: str) -> str:
    section = text.split(heading, 1)[1]
    return section.split("```python", 1)[1].split("```", 1)[0]


def test_readme_quick_start_features_only_the_two_entry_points() -> None:
    text = (_ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = text.split("## Quick Start", 1)[1].split("### Verify locally and on Azure", 1)[0]
    assert "logging_context" in quick_start
    assert "with_context" in quick_start
    assert "inject_context" not in quick_start
    assert "restore_context" not in quick_start
    assert "inject_context" not in _first_python_block_after(text, "## Quick Start")


def test_api_reference_labels_inject_context_low_level() -> None:
    text = (_ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    section = text.split("## inject_context", 1)[1].split("## with_context", 1)[0]
    assert "Low-level" in section and "restore_context" in section
