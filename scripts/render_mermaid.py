#!/usr/bin/env python3
"""Render-lint Mermaid diagrams embedded in Markdown to catch syntax errors.

Unlike ``lint_mermaid.py`` (label-hygiene only), this script actually renders
every ```mermaid``` fenced block with the Mermaid CLI (``mmdc``). Invalid
syntax that a text linter cannot detect will fail the render, and therefore CI.

Because ``mmdc`` pulls in a headless-Chromium dependency, this check is kept in
an isolated workflow rather than the main docs build.

Usage::

    python scripts/render_mermaid.py [FILE ...]

With no arguments, the default target globs are scanned. Explicit file
arguments (e.g. the changed files on a PR) are used as-is when provided.

Exit code 0 when every diagram renders, 1 when any diagram fails to render or
when ``mmdc`` is unavailable.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

# Files/globs to scan, relative to the repository root.
TARGET_GLOBS = ("README*.md", "DESIGN.md", "docs/**/*.md")

FENCE_START = "```mermaid"
FENCE_END = "```"

REPO_ROOT = Path(__file__).resolve().parent.parent
# Puppeteer config so Chromium runs in sandboxed CI containers.
PUPPETEER_CONFIG = REPO_ROOT / "scripts" / "puppeteer-config.json"


def _iter_default_targets() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in TARGET_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return files


def _extract_blocks(path: Path) -> list[tuple[int, str]]:
    """Return (start_line, source) for each Mermaid block in *path*."""
    blocks: list[tuple[int, str]] = []
    in_block = False
    start_line = 0
    buffer: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not in_block:
            if stripped.startswith(FENCE_START):
                in_block = True
                start_line = lineno
                buffer = []
            continue
        if stripped == FENCE_END:
            in_block = False
            blocks.append((start_line, "\n".join(buffer)))
            continue
        buffer.append(raw)
    return blocks


def _render(source: str, workdir: Path) -> tuple[bool, str]:
    """Render one Mermaid *source*; return (ok, message)."""
    src = workdir / "diagram.mmd"
    out = workdir / "diagram.svg"
    src.write_text(source + "\n", encoding="utf-8")
    cmd = [
        "mmdc",
        "--input",
        str(src),
        "--output",
        str(out),
        "--quiet",
    ]
    if PUPPETEER_CONFIG.is_file():
        cmd += ["--puppeteerConfigFile", str(PUPPETEER_CONFIG)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, detail
    return True, ""


def main(argv: list[str]) -> int:
    if shutil.which("mmdc") is None:
        print(
            "error: 'mmdc' (mermaid-cli) not found on PATH. "
            "Install with: npm install -g @mermaid-js/mermaid-cli",
            file=sys.stderr,
        )
        return 1

    if argv:
        targets = [Path(a) for a in argv if Path(a).is_file()]
    else:
        targets = _iter_default_targets()

    failures: list[str] = []
    rendered = 0
    for path in targets:
        for start_line, source in _extract_blocks(path):
            if not source.strip():
                continue
            with tempfile.TemporaryDirectory() as tmp:
                ok, detail = _render(source, Path(tmp))
            if ok:
                rendered += 1
            else:
                failures.append(f"{path}:{start_line}: Mermaid render failed\n{detail}")

    if failures:
        print("Mermaid render lint FAILED:\n", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
            print("", file=sys.stderr)
        return 1

    print(f"Mermaid render lint OK: {rendered} diagram(s) rendered cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
