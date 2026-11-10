"""The committed historical exceptions, exercised against the audit with fixtures (#667).

The generic behaviour is covered by ``test_release_audit.py``. These cases use this repository's
own history: a fully published release, the ``v0.15.1`` and ``v0.15.2`` candidates whose host-boot
smoke failed before publish, and an early published version that had no GitHub Release.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools import release_audit as ra

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=30)
CFG = ra.Config.load(ROOT / ra.CONFIG_PATH)


def tag(version: str, declared: str | None = None, on_mainline: bool = True) -> ra.TagFact:
    return ra.TagFact(f"v{version}", "a" * 40, OLD, declared or version, on_mainline)


def release(version: str) -> ra.ReleaseFact:
    return ra.ReleaseFact(f"v{version}", False, OLD)


def pypi(version: str) -> ra.PyPIFact:
    return ra.PyPIFact(version, False, OLD)


def facts(
    tags: list[ra.TagFact],
    releases: list[ra.ReleaseFact],
    published: list[ra.PyPIFact],
    changelog: set[str],
) -> ra.Facts:
    return ra.Facts(
        tags={t.name.removeprefix("v"): t for t in tags},
        releases={r.tag.removeprefix("v"): r for r in releases},
        pypi={p.version: p for p in published},
        changelog_versions=frozenset(changelog),
    )


def only(*versions: str) -> ra.Config:
    """The committed exceptions for just these versions, so a one-version fixture is not stale."""
    return ra.Config(
        repo=CFG.repo,
        package=CFG.package,
        mainline=CFG.mainline,
        approved={v: CFG.approved[v] for v in versions},
    )


def test_the_committed_exceptions_are_exactly_the_documented_cases() -> None:
    assert set(CFG.approved) == {"0.15.1", "0.15.2"}
    assert CFG.approved["0.15.1"].codes == {ra.RELEASE_WITHOUT_PYPI}
    assert CFG.approved["0.15.2"].codes == {ra.RELEASE_WITHOUT_PYPI}


def test_a_fully_published_release_is_clean() -> None:
    clean = facts([tag("0.16.0")], [release("0.16.0")], [pypi("0.16.0")], {"0.16.0"})
    report = ra.audit(only(), clean, NOW)
    assert report.ok
    assert report.findings == ()


def test_the_unpublished_candidates_are_documented_exceptions_not_new_defects() -> None:
    candidates = facts(
        [tag("0.15.1"), tag("0.15.2")],
        [release("0.15.1"), release("0.15.2")],
        [],
        {"0.15.1", "0.15.2"},
    )
    assert not ra.audit(only(), candidates, NOW).ok
    report = ra.audit(only("0.15.1", "0.15.2"), candidates, NOW)
    assert report.ok
    assert [f.approved for f in report.findings] == [(ra.RELEASE_WITHOUT_PYPI,)] * 2


def test_a_new_unpublished_release_is_still_reported_next_to_the_exceptions() -> None:
    both = facts(
        [tag("0.15.1"), tag("0.17.0")],
        [release("0.15.1"), release("0.17.0")],
        [],
        {"0.15.1", "0.17.0"},
    )
    report = ra.audit(only("0.15.1"), both, NOW)
    assert not report.ok
    assert [f.version for f in report.findings if f.failing] == ["0.17.0"]


def test_an_exception_does_not_cover_the_neighbouring_candidate() -> None:
    candidates = facts(
        [tag("0.15.1"), tag("0.15.2")],
        [release("0.15.1"), release("0.15.2")],
        [],
        {"0.15.1", "0.15.2"},
    )
    report = ra.audit(only("0.15.1"), candidates, NOW)
    assert not report.ok
    assert [f.version for f in report.findings if f.failing] == ["0.15.2"]


def test_a_published_early_tag_without_a_github_release_is_reported() -> None:
    early = facts([tag("0.2.0")], [], [pypi("0.2.0")], {"0.2.0"})
    report = ra.audit(only(), early, NOW)
    assert not report.ok
    assert report.findings[0].unapproved == (ra.PYPI_WITHOUT_RELEASE,)
    assert ra.audit(
        only(), facts([tag("0.2.0")], [release("0.2.0")], [pypi("0.2.0")], {"0.2.0"}), NOW
    ).ok
