# Review Evidence Policy (advisory)

> **Status: advisory, not server-enforced.** Nothing in this document is a required status
> check. Branch protection on `main` still gates only on the five required contexts
> (`ci-required`, `bandit`, `semgrep`, `Analyze`, `PR title`), strict mode, and conversation
> resolution — see [#459's final decision](https://github.com/yeongseon/azure-functions-logging-python/issues/459#issuecomment-5963270562).
> This policy defines what review *evidence* a maintainer should record before merging; it does
> not add a required check, and must not be treated as one until a trusted verdict publisher is
> configured and verified in this repository (see "Rollout" below).

This repository runs with **zero required native GitHub approvals** (#459) because the sole
maintainer cannot approve their own PR, and a review requirement would block every PR. Independent
review still happens — Copilot code review, or a human — but nothing previously recorded *who*
reviewed *which commit*, *what* was found, or whether findings were resolved before merge. The
existing PR template's **Verification** and **Not run** sections already record command/
environment/result evidence; this document adds the reviewer-identity and findings-disposition
record those sections don't cover. It does **not** reopen #459 (zero native approvals stands) and
does **not** replace CI.

## Roles

- **Implementer** — the person or agent that authored the change (may be the maintainer).
- **Independent reviewer** — a review source distinct from the implementer: GitHub Copilot code
  review, or a human maintainer/contributor who did not author the diff. A review is only
  independent evidence if it evaluates the PR's **current head commit**; a thread opened against
  an earlier commit is stale once the diff changes (see "SHA binding" below).

Implementer-managed helper reviews (e.g. an agent re-running its own linter and calling the result
a "review") are supplemental context, not independent review evidence. A checklist, comment state,
or reaction alone is insufficient.

## SHA binding (why this matters)

A review is evidence for the commit it evaluated — never for the PR as a whole:

- Use the **formal review's reviewed commit** (`reviews[].commit_id` via the GitHub API), not an
  inline comment's current `commit_id`. GitHub can re-target an inline comment's `commit_id` to the
  latest push even when the comment's `original_commit_id` still names the commit it was actually
  left against.
- A reply to an existing review thread — including one authored by the PR's own implementer — is
  not a new independent review of the diff, even when it is the most recent activity on the final
  head.
- Any push after a review invalidates that review's evidence for the new head.

## Review effort

Seek additional review when risk or unresolved findings justify it, without a mandatory number of AI review rounds. Maintain explicit human review for high-risk changes.

## What to record per PR

For routine PRs, record a short summary, key changes, actual validation, and related issues. State significant findings and blockers when relevant. Do not require risk tiers, evidence placeholders, or agent process logs on ordinary PRs.

For changes in the high-risk R3 scope below, additionally record the reviewed commit, material findings, and explicit maintainer authorization. This evidence can be a short dedicated section; AI review does not itself establish human approval.

- For changes to Logging's public contracts specifically: invocation/context isolation across
  concurrent work and generator lifetimes, handler-local record mutation (`IsolatedHandler`),
  structured output and redaction, sanitized exception diagnostics, Azure worker handler ownership,
  or opt-in OpenTelemetry correlation — which contract is touched, and the test(s) that exercise
  it. Evidence here can be local and use dummy/synthetic sensitive values; live telemetry ingestion
  or publication is a separate claim this policy does not make.

External contributors may use ordinary human review without subscriptions or AI tooling.

## R3 scope

Treat the following as higher-risk ("R3") and require an explicit human maintainer authorization
record tied to the reviewed commit, in addition to any automated review:

- Workflow permissions (`permissions:` blocks, `GITHUB_TOKEN` scope, secrets usage).
- Release/publishing configuration (`publish-pypi.yml`, `release-please.yml`, PyPI Trusted
  Publishing config).
- Security-sensitive redaction or log/exception-disclosure behavior (`_redaction.py`,
  `_filters.py`'s `RedactionFilter`/`AttributeFlattenFilter`, `_isolated_handler.py`, and anything
  touching what reaches a sink from `extra=` payloads or `exc_info`).
- Telemetry trust boundaries — what context/trace data crosses into OpenTelemetry or Application
  Insights (`_otel.py`, `_host_config.py`'s OTel detection).
- Review policy or evaluator configuration itself — changes to this document, reviewer allowlists,
  or `CODEOWNERS` if introduced.
- Policy-bearing files generally: `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `docs/agent-playbook.md`, `.github/PULL_REQUEST_TEMPLATE.md`, this document.

An account token, an automatically posted comment, the merge actor, or a successful CI run does
not by itself prove a human authorized an R3 change — record who actually made the call, on which
commit, and why.

## Exceptions (explicit policy cases)

These are documented **exceptions**, not instances of independent review — they remain visible as
exceptions in PR history rather than being recorded as if a review had occurred:

- **Release Please** PRs: version/changelog-only; mechanical, not independently reviewed.
- **Dependabot `pip` patch/minor**: auto-merged on green required CI; the full test matrix is the
  evidence. Note the auto-merge workflow uses `secrets.GITHUB_TOKEN`, which cannot itself approve a
  PR (#459) — auto-merge here relies on the zero-required-approvals policy, not on the token
  granting approval.
- **GitHub Actions SHA updates**: require a human diff check confirming the pinned SHA matches its
  claimed tag. This human check *is* the review evidence — record the SHA/tag comparison
  performed.
- **Forks**: external PRs are reviewed by a maintainer before merge; Copilot review may be
  unavailable or restricted on fork PRs depending on repository settings — record "unavailable"
  explicitly rather than silently skipping the field.
- **Reviewer outages / emergencies**: if Copilot review is unavailable (quota, outage, provider
  error), record the unavailability and fall back to human review before merge.

## Provenance pitfalls (do not accept as evidence)

- A bot `COMMENTED` or `APPROVED` state alone does not prove independent human authorization —
  check reviewer identity/type, not just the review state.
- A shared GitHub Actions app ID (15368, observed across sampled PRs #575/#573/#572) is not
  sufficient to identify the trusted evaluator: any PR-controlled workflow can emit a result under
  the same app ID. Verdict-publisher identity must be resolved before any such result is treated as
  enforced evidence (see "Rollout").
- An unknown or missing response must never default to "approved" — treat it as "evidence absent."
- A resolved review thread does not establish the findings were addressed on the *current* head if
  the thread's reviewed commit predates later pushes.

## Rollout

This policy begins **advisory-only**. Before any of it becomes a required, server-enforced check:

1. The verdict-publisher's identity must be independently resolved (not just a shared app ID) and
   documented.
2. The exact required-check binding (context name + trusted publisher) must be configured and
   verified against this repository's branch protection (full protection reads returned HTTP 403
   in the reviewed pass — re-verify before relying on any cached assumption about current
   settings).
3. Administrator/emergency bypass boundaries for that check must be documented alongside the
   existing `enforce_admins=false` emergency-bypass policy.

Until all three are done, nothing in this document overrides or supersedes the required CI
contexts, strict mode, and conversation-resolution policy already enforced on `main`.

## Related work

- [#459](https://github.com/yeongseon/azure-functions-logging-python/issues/459) — the
  zero-native-approval decision this policy builds on, not reopens.
- [#463](https://github.com/yeongseon/azure-functions-logging-python/issues/463) — prior,
  completed contributor/template cleanup.
- [#557](https://github.com/yeongseon/azure-functions-logging-python/issues/557) — prior,
  completed runtime/release tracker; not reopened by this policy.
