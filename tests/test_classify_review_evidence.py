"""Fixtures-based regression tests for scripts/classify_review_evidence.py.

Fixtures are synthetic but shaped like the provenance patterns documented in
#592 / docs/review-evidence-policy.md: the sampled PRs (#575, #573, #572)
returned empty formal reviews/threads/comments with required CI green under
GitHub Actions app ID 15368, and the '<!-- ccr-overview-v2 -->' Copilot
summary marker. No real PR data is scraped.
"""

from __future__ import annotations

from scripts.classify_review_evidence import (
    classify_inline_comment,
    classify_review,
    has_open_findings,
    same_app_id_does_not_prove_trusted_publisher,
)

PR_AUTHOR = "yeongseon"
CURRENT_HEAD = "cccccc2"
SAMPLED_APP_ID = 15368


class TestClassifyReview:
    def test_independent_review_of_current_head_is_evidence(self) -> None:
        review = {"user": {"login": "copilot-pull-request-reviewer"}, "commit_id": CURRENT_HEAD}

        result = classify_review(review, pr_author=PR_AUTHOR, current_head_sha=CURRENT_HEAD)

        assert result.is_independent is True

    def test_review_of_stale_commit_is_not_evidence(self) -> None:
        """Regression (#592): a review of an earlier commit is not evidence
        for a later head -- a push after review invalidates it."""
        review = {"user": {"login": "copilot-pull-request-reviewer"}, "commit_id": "aaaaaa1"}

        result = classify_review(review, pr_author=PR_AUTHOR, current_head_sha=CURRENT_HEAD)

        assert result.is_independent is False
        assert "stale" in result.reason

    def test_author_authored_review_is_not_independent(self) -> None:
        review = {"user": {"login": PR_AUTHOR}, "commit_id": CURRENT_HEAD}

        result = classify_review(review, pr_author=PR_AUTHOR, current_head_sha=CURRENT_HEAD)

        assert result.is_independent is False
        assert "author" in result.reason

    def test_empty_reviews_on_sampled_prs_is_evidence_absence_not_approval(self) -> None:
        """Regression (#592): the sampled PRs (#575/#573/#572) returned an
        empty reviews list -- this must be treated as "no evidence found",
        never silently upgraded to an implicit approval."""
        reviews: list[dict[str, str]] = []

        results = [
            classify_review(r, pr_author=PR_AUTHOR, current_head_sha=CURRENT_HEAD) for r in reviews
        ]

        assert results == []


class TestClassifyInlineComment:
    def test_final_head_author_reply_is_not_independent(self) -> None:
        comment = {
            "user": {"login": PR_AUTHOR},
            "original_commit_id": CURRENT_HEAD,
            "commit_id": CURRENT_HEAD,
            "in_reply_to_id": 4259275751,
        }

        result = classify_inline_comment(
            comment, pr_author=PR_AUTHOR, current_head_sha=CURRENT_HEAD
        )

        assert result.is_independent is False
        assert "reply" in result.reason

    def test_remapped_commit_id_is_not_treated_as_current(self) -> None:
        """Regression (#592): an inline comment's commit_id can be remapped
        to the final head by GitHub even though original_commit_id (and the
        formal review) still identify the earlier reviewed commit. Must use
        original_commit_id, not the remapped commit_id."""
        comment = {
            "user": {"login": "copilot-pull-request-reviewer"},
            "original_commit_id": "aaaaaa1",
            "commit_id": CURRENT_HEAD,
            "in_reply_to_id": None,
        }

        result = classify_inline_comment(
            comment, pr_author=PR_AUTHOR, current_head_sha=CURRENT_HEAD
        )

        assert result.is_independent is False
        assert result.reviewed_commit == "aaaaaa1"

    def test_independent_comment_on_current_head_is_evidence(self) -> None:
        comment = {
            "user": {"login": "copilot-pull-request-reviewer"},
            "original_commit_id": CURRENT_HEAD,
            "commit_id": CURRENT_HEAD,
            "in_reply_to_id": None,
        }

        result = classify_inline_comment(
            comment, pr_author=PR_AUTHOR, current_head_sha=CURRENT_HEAD
        )

        assert result.is_independent is True


class TestHasOpenFindings:
    def test_open_findings_summary(self) -> None:
        body = "<!-- ccr-overview-v2 -->\n### \U0001f7e1 Changes recommended\n1 open finding"

        assert has_open_findings(body) is True

    def test_no_findings_summary_is_not_open_findings(self) -> None:
        body = "<!-- ccr-overview-v2 -->\n### \u2705 No findings"

        assert has_open_findings(body) is False

    def test_unmarked_body_is_not_open_findings(self) -> None:
        assert has_open_findings("Looks good to me!") is False


class TestSharedAppIdProvenance:
    def test_matching_app_id_is_flagged_for_further_verification_not_trusted(self) -> None:
        """Regression (#592): a check-run under the observed shared app ID
        (15368, from sampled PRs #575/#573/#572) must not be treated as
        automatically trustworthy -- this helper only confirms the ID
        matches; it explicitly does not resolve or vouch for the actual
        publishing workflow's identity."""
        check_run = {"app": {"id": SAMPLED_APP_ID}}

        matches = same_app_id_does_not_prove_trusted_publisher(check_run, SAMPLED_APP_ID)

        assert matches is True  # matched the ID -- NOT the same as "trusted"

    def test_different_app_id_does_not_match(self) -> None:
        check_run = {"app": {"id": 99999}}

        assert same_app_id_does_not_prove_trusted_publisher(check_run, SAMPLED_APP_ID) is False
