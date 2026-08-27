"""Regression guard for the documentation external-link tag-integrity lint.

Exercises tools/lint_doc_links.py against this repo (must be clean) and against
synthetic drift (must be caught). Keeps the vendored lint honest.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

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


class _FakeResp:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_verify_refs_checks_full_url_and_passes_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """--verify-refs must HEAD the full citation URL (ref + path), not a truncated one."""
    lint_mod._ref_exists.cache_clear()
    seen: list[str] = []

    def fake_urlopen(req, timeout=10.0):  # type: ignore[no-untyped-def]
        seen.append(req.full_url)
        return _FakeResp(200)

    monkeypatch.setattr(lint_mod, "urlopen", fake_urlopen)
    url = "https://github.com/Azure/proto/blob/v1.0.0/src/proto/FunctionRpc.proto"
    text = f"See [proto]({url}#L10).\n"
    errors = lint_mod.check_links(text, "fake.md", verify_refs=True)
    assert errors == []
    # The full path (ref + file path) is verified, not just up through the ref.
    assert seen == [url]


def test_verify_refs_fails_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """A definitive 404 on the full citation URL must be reported as drift."""
    lint_mod._ref_exists.cache_clear()
    seen: list[str] = []

    def fake_urlopen(req, timeout=10.0):  # type: ignore[no-untyped-def]
        seen.append(req.full_url)
        raise lint_mod.HTTPError(req.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(lint_mod, "urlopen", fake_urlopen)
    url = "https://raw.githubusercontent.com/Azure/lib/2.2.0/azure/functions/_missing.py"
    text = f"{url}\n"
    errors = lint_mod.check_links(text, "fake.md", verify_refs=True)
    assert errors and "does not" in errors[0] and url in errors[0]
    assert seen == [url]


def test_verify_refs_caches_per_unique_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated occurrences of the same URL trigger a single network call."""
    lint_mod._ref_exists.cache_clear()
    calls: list[str] = []

    def fake_urlopen(req, timeout=10.0):  # type: ignore[no-untyped-def]
        calls.append(req.full_url)
        return _FakeResp(200)

    monkeypatch.setattr(lint_mod, "urlopen", fake_urlopen)
    url = "https://github.com/Azure/proto/blob/v1.0.0/a.proto"
    text = f"{url}\n{url}\n{url}\n"
    errors = lint_mod.check_links(text, "fake.md", verify_refs=True)
    assert errors == []
    assert calls == [url]
