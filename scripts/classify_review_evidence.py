"""Classify GitHub PR review/comment records against the review-evidence
policy (#592, see docs/review-evidence-policy.md).

Advisory-only helper: given a review or inline-comment record shaped like
the GitHub REST API response, classify whether it counts as independent
review evidence for a given head commit, or is one of the documented
provenance pitfalls (author reply, stale commit, remapped inline comment).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CCR_OPEN_FINDINGS_MARKER = "<!-- ccr-overview-v2 -->"
_CHANGES_RECOMMENDED_TEXT = "Changes recommended"


@dataclass(frozen=True, slots=True)
class ReviewEvidence:
    reviewer: str
    reviewed_commit: str
    is_independent: bool
    reason: str


def classify_review(
    review: dict[str, Any], *, pr_author: str, current_head_sha: str
) -> ReviewEvidence:
    """Classify a formal PR review (``GET /pulls/{n}/reviews`` entry)."""
    reviewer = review.get("user", {}).get("login", "<unknown>")
    commit = review.get("commit_id", "")
    if reviewer == pr_author:
        return ReviewEvidence(reviewer, commit, False, "author-authored review is not independent")
    if commit != current_head_sha:
        return ReviewEvidence(
            reviewer, commit, False, "reviewed commit is stale relative to the current head"
        )
    return ReviewEvidence(reviewer, commit, True, "independent review of the current head")


def classify_inline_comment(
    comment: dict[str, Any], *, pr_author: str, current_head_sha: str
) -> ReviewEvidence:
    """Classify an inline PR comment (``GET /pulls/{n}/comments`` entry).

    Uses ``original_commit_id`` rather than ``commit_id``: GitHub can
    re-target an inline comment's ``commit_id`` to the latest push even
    when the comment was left against an earlier commit, so ``commit_id``
    alone cannot be trusted as evidence of re-review (#592).
    """
    reviewer = comment.get("user", {}).get("login", "<unknown>")
    original_commit = comment.get("original_commit_id") or comment.get("commit_id", "")
    if comment.get("in_reply_to_id") is not None:
        return ReviewEvidence(
            reviewer,
            original_commit,
            False,
            "reply to an existing review thread, not a new independent review",
        )
    if reviewer == pr_author:
        return ReviewEvidence(
            reviewer, original_commit, False, "author-authored comment is not independent"
        )
    if original_commit != current_head_sha:
        return ReviewEvidence(
            reviewer,
            original_commit,
            False,
            "comment predates the current head; current commit_id may be remapped",
        )
    return ReviewEvidence(
        reviewer, original_commit, True, "independent comment on the current head"
    )


def has_open_findings(review_body: str) -> bool:
    """Return True for a Copilot review summary reporting open findings."""
    return CCR_OPEN_FINDINGS_MARKER in review_body and _CHANGES_RECOMMENDED_TEXT in review_body


def same_app_id_does_not_prove_trusted_publisher(check_run: dict[str, Any], app_id: int) -> bool:
    """Return True if a check-run's app ID matches the observed shared app ID.

    Matching alone is NOT sufficient to treat the result as a trusted
    verdict (#592): any PR-controlled workflow can emit a check-run under
    the same GitHub Actions app ID (observed as 15368 across this
    repository's sampled PRs #575/#573/#572). This helper exists to make
    that comparison explicit and testable, not to approve anything by
    itself -- callers must still resolve the actual publishing workflow's
    identity before trusting a result.
    """
    return bool(check_run.get("app", {}).get("id") == app_id)
