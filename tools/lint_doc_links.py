#!/usr/bin/env python3
"""External-link tag-integrity lint for documentation.

Part of the DX Toolkit CI hardening work (sibling to
``tools/lint_workflow_pins.py``). Where that lint keeps GitHub Actions pinned to
immutable commit SHAs, this lint keeps **documentation citations** pinned to
immutable refs.

Motivation -- a docs page that cites external source code with a
``/blob/main/...`` link is citing a *moving target*: the referenced line can
shift or disappear on the next upstream commit, silently invalidating the claim
the docs page makes. Citations must therefore point at an immutable ref (a
release tag or a 40-hex commit SHA), never a branch.

Rule -- every external GitHub source link (``/blob/``, ``/tree/``, ``/raw/`` on
``github.com``, or any ``raw.githubusercontent.com`` link) MUST resolve to an
immutable ref:

1. A full 40-hex commit SHA; or
2. A ref that is not a known mutable branch name (treated as a tag).

Links to the project's own repositories (owners in ``SELF_OWNERS``) are skipped:
they intentionally track the living repo and are not third-party citations.

With ``--verify-refs`` the lint additionally makes a network request per unique
link and fails on a definitive ``404`` (a tag/SHA/path that does not exist).
Transient network errors are reported as warnings and never fail the run, so the
scheduled job does not flake on rate limits or offline runners.

Stdlib-only on purpose: the lint must not itself depend on a package that can
drift. Exit code 0 = clean, 1 = drift detected.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Files whose external citations must be immutable.
DOC_GLOBS = ("README*.md", "DESIGN.md", "docs/**/*.md")

# Owners whose links track the living project repo, not third-party citations.
SELF_OWNERS = {"yeongseon"}

# Refs that move over time; citing them defeats the point of a permalink.
MUTABLE_REFS = {
    "main",
    "master",
    "head",
    "dev",
    "develop",
    "trunk",
    "latest",
    "next",
    "stable",
    "gh-pages",
}

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# github.com/<owner>/<repo>/(blob|tree|raw)/<ref>/<path...>
_GH_BLOB_RE = re.compile(
    r"https://github\.com/"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/"
    r"(?:blob|tree|raw)/"
    r"(?P<ref>[^/\s#)]+)"
)
# raw.githubusercontent.com/<owner>/<repo>/<ref>/<path...>
_GH_RAW_RE = re.compile(
    r"https://raw\.githubusercontent\.com/"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/"
    r"(?P<ref>[^/\s#)]+)"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _iter_doc_files(root: Path) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in DOC_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return files


def _ref_exists(url: str, *, timeout: float = 10.0) -> tuple[bool | None, str]:
    """Return (exists, note). ``None`` means indeterminate (transient error)."""
    req = Request(url, method="HEAD", headers={"User-Agent": "doc-link-lint"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            return (200 <= resp.status < 400, f"HTTP {resp.status}")
    except HTTPError as exc:
        if exc.code == 404:
            return (False, "HTTP 404")
        # 403/429/5xx: rate-limited or transient, do not fail the build.
        return (None, f"HTTP {exc.code}")
    except (URLError, TimeoutError, OSError) as exc:  # pragma: no cover - network
        return (None, f"network error: {exc}")


def check_links(text: str, rel_path: str, *, verify_refs: bool = False) -> list[str]:
    """Assert every external GitHub source link points at an immutable ref."""
    errors: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in (_GH_BLOB_RE, _GH_RAW_RE):
            for m in pattern.finditer(line):
                owner = m.group("owner")
                if owner in SELF_OWNERS:
                    continue
                ref = m.group("ref")
                if _SHA_RE.match(ref):
                    pass
                elif ref.lower() in MUTABLE_REFS:
                    errors.append(
                        f"{rel_path}:{lineno}: external link pinned to mutable "
                        f"ref '{ref}' ({owner}/{m.group('repo')}); cite a release "
                        f"tag or 40-hex commit SHA instead of a branch"
                    )
                    continue
                if verify_refs:
                    exists, note = _ref_exists(m.group(0))
                    if exists is False:
                        errors.append(
                            f"{rel_path}:{lineno}: external link ref does not "
                            f"exist ({note}): {m.group(0)}"
                        )
                    elif exists is None:
                        print(
                            f"  ~ {rel_path}:{lineno}: could not verify "
                            f"{m.group(0)} ({note}); skipping",
                            file=sys.stderr,
                        )
    return errors


def lint(root: Path | None = None, *, verify_refs: bool = False) -> list[str]:
    """Run tag-integrity over every doc file; return human-readable violations."""
    root = root or _repo_root()
    errors: list[str] = []
    for path in _iter_doc_files(root):
        rel = path.relative_to(root).as_posix()
        errors.extend(check_links(path.read_text(encoding="utf-8"), rel, verify_refs=verify_refs))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-refs",
        action="store_true",
        help="Also make a network request per link and fail on a definitive 404.",
    )
    args = parser.parse_args(argv)

    errors = lint(verify_refs=args.verify_refs)
    if errors:
        print("Documentation external-link tag-integrity drift detected:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Documentation links: every external GitHub citation is immutably pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
