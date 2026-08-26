"""Regression guard for the documentation external-link tag-integrity lint.

Exercises tools/lint_doc_links.py against this repo (must be clean) and against
synthetic drift (must be caught). Keeps the vendored lint honest.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LINT_PATH = _REPO_ROOT / "tools" / "lint_doc_links.py"

_spec = importlib.util.spec_from_file_location("lint_doc_links", _LINT_PATH)
assert _spec and _spec.loader
lint_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint_mod)


def test_repo_docs_are_link_clean() -> None:
    """Every committed doc must cite external source at an immutable ref."""
    assert lint_mod.lint() == []


def test_sha_blob_link_passes() -> None:
    sha = "a" * 40
    text = f"See [proto](https://github.com/Azure/proto/blob/{sha}/x.proto#L1).\n"
    assert lint_mod.check_links(text, "fake.md") == []


def test_tag_blob_link_passes() -> None:
    text = "See [ctx](https://github.com/Azure/lib/blob/v1.14.0-protofile/a.py#L2).\n"
    assert lint_mod.check_links(text, "fake.md") == []


def test_raw_tag_link_passes() -> None:
    text = "https://raw.githubusercontent.com/Azure/lib/2.2.0/azure/functions/_abc.py\n"
    assert lint_mod.check_links(text, "fake.md") == []


def test_self_owner_main_link_is_skipped() -> None:
    text = "https://github.com/yeongseon/azure-functions-logging-python/blob/main/README.md\n"
    assert lint_mod.check_links(text, "fake.md") == []


def test_external_main_blob_fails() -> None:
    text = "https://github.com/Azure/proto/blob/main/src/proto/FunctionRpc.proto\n"
    errors = lint_mod.check_links(text, "fake.md")
    assert errors and "mutable ref 'main'" in errors[0]


def test_external_master_tree_fails() -> None:
    text = "https://github.com/Azure/lib/tree/master/azure\n"
    errors = lint_mod.check_links(text, "fake.md")
    assert errors and "mutable ref 'master'" in errors[0]


def test_external_raw_main_fails() -> None:
    text = "https://raw.githubusercontent.com/Azure/lib/main/azure/functions/_abc.py\n"
    errors = lint_mod.check_links(text, "fake.md")
    assert errors and "mutable ref 'main'" in errors[0]
