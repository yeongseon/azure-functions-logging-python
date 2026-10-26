# Review and merge evidence

This is the single source for review records. It adds no workflow, reviewer bot,
paid-tool requirement or required status check. AI feedback is advice, never
human approval or proof that tests ran.

## Every change

1. Describe the change and link its tracking issue. Record commands actually run,
   their environment/results, and material checks not run in the PR's Validation
   section. Do not add empty evidence fields or mandatory AI review rounds.
2. Read the current diff for correctness, compatibility, maintainability and
   security. Evaluate findings against the code; fix valid findings or explain
   their disposition, and resolve review conversations.
3. Before merging, confirm the required contexts (`bandit`, `semgrep`, `Analyze`,
   `PR title`, `ci-required`) pass on the exact current head, with the branch
   up to date and all conversations resolved. A review of an older commit is
   evidence only for that older commit; review substantive changes made since it.
4. Record the responsible maintainer's merge decision. Zero required GitHub
   approvals allows a sole maintainer to merge; it does not make an AI review
   a human approval or permit bypassing CI.

External contributors can follow this procedure using ordinary human review and
GitHub CI; no subscription or local review agent is necessary.

## Security-sensitive and policy changes

Additionally record the reviewed head SHA, material findings/dispositions, the
affected contract and relevant tests, and explicit maintainer authorization.
This applies to credentials, permissions, release/publishing, redaction and
exception disclosure, handler ownership/mutation, concurrent invocation context
isolation, telemetry trust boundaries, and repository policy changes.

A token, bot review state, merge actor or successful CI run alone is not evidence
of human authorization. State who authorized the change and why. Synthetic local
tests may establish a logging contract; they do not establish live ingestion or
Azure certification. Obtain further review when unresolved risk warrants it,
not to satisfy a fixed number of AI rounds.

## Compact PR examples

Routine change:

```text
Summary: clarify exporter-first setup; no runtime change.
Validation: make check-all and make build passed on Python 3.11; exact test
summary recorded. Live Azure ingestion not run (documentation-only change).
Related Issues: Closes #N
Merge decision: maintainer accepted the current diff with required CI green.
```

Security-sensitive change adds only the relevant detail:

```text
Review: head <SHA>; protects exception diagnostics before sink translation.
Finding: raw cached traceback could bypass masking; fixed and covered by the
downstream synthetic-canary regression. No unresolved findings.
Authorization: <maintainer> explicitly authorized this reviewed change because
the disclosure regression is fixed; exact-head required CI is green.
```

## Automated and dependency PRs

- Pip patch/minor Dependabot updates may auto-merge after required CI passes;
  AI review is not a prerequisite. Major updates need a compatibility decision.
- GitHub Actions updates never auto-merge: review the version-only diff, compare
  each pinned SHA with its claimed tag (dereference annotated tags), and record
  the comparison before merging.
- Release Please version/changelog PRs follow the release process and existing
  release gates. A mechanical diff is not a claim of independent review.
- A maintainer reviews externally authored PRs before merge. If an optional AI
  reviewer is unavailable, ordinary human review remains sufficient; no empty
  outage/provenance form is required.

Branch protection and the release/security safeguards remain unchanged. Nothing
here introduces an evaluator publisher, relaxes a required check, or authorizes
an administrator bypass.
