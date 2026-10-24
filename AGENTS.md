# AGENTS.md

## Purpose
`azure-functions-logging` provides structured JSON logging for Azure Functions Python v2 applications.

## Repository Identity
- Project: `azure-functions-logging`
- Project type: Python library
- Runtime scope: Azure Functions Python v2 programming model
- Minimum supported Python: `3.11`
- Packaging: `pyproject.toml` with Hatch

## Read First
- `README.md`
- `CONTRIBUTING.md`

## Working Rules

### Test Coverage
- Maintain test coverage at **95% or above** for committed changes and PRs.
- For optional local verification, run `hatch run pytest --cov --cov-report=term-missing -q`; required GitHub CI remains authoritative.
- Any PR that drops coverage below 95% must include additional tests to compensate.
- In Azure/Core Tools mode, `setup_logging()` installs `ContextFilter` on the root logger's existing handlers (and the root logger itself for late-attaching handlers) but never adds new handlers or changes the root level. When `use_record_factory=True`, no `ContextFilter` is attached; context is injected via the global `LogRecordFactory` instead. In standalone local mode, the root logger is configured by default (`logger_name=None`); pass an explicit `logger_name` to avoid modifying the root logger.
- `azure-functions>=1.21.0` is a required runtime dependency (declared in `pyproject.toml`, added deliberately in #528 to align the toolkit floor). OpenTelemetry support remains an optional `[otel]` extra, imported only when `activate_trace_context=True` is used.
- Runtime code must remain compatible with Python 3.11-3.14 (`>=3.11,<3.15`).
- Public APIs must be fully typed.
- Keep documentation examples and tests synchronized with any behavior changes.

### Documentation & Translations
- English (`README.md`) is the **canonical** source of truth for all documentation. Translated READMEs (`README.ko.md`, `README.ja.md`, `README.zh-CN.md`) are **best-effort**, community-maintained, and may lag the English source.
- Translation sync is **not** required in the same PR as an English change, and a PR is **never** blocked by translation drift. Update translations opportunistically; when you do, keep them faithful to the current English source.
- Each translated README carries a staleness banner linking back to the canonical English README. Keep that banner in place so readers always know the translation may be out of date.

## Unified PR Review and Merge Policy

Apply the same review standards to human-authored changes and code produced
with OpenCode, Codex, Claude Code, ChatGPT, Copilot or any other agent.
There is **no required AI-specific design, code review or approval route**.

1. Submit a focused, issue-linked PR with appropriate tests, docs and risks.
2. Use **GitHub CI** required checks on the final relevant PR head as the
   authoritative validation record; local checks are useful but optional.
   Preserve coverage thresholds, documentation, security, Azure integration
   and release/publishing safeguards. Do not assume a specific CI runner.
3. Evaluate behavior, security, regressions and maintainability. Oracle,
   Copilot and `agent-review` may provide optional **advisory** observations,
   but do not substitute for human review or actual test execution.
4. Resolve or disposition findings and let the responsible maintainer
   make the merge decision after confirming final CI. High-impact
   security, credential, workflow and release changes need explicit
   independent scrutiny.

## Issue Conventions

Follow these conventions when opening or editing issues in this repository.

### Repository scope

- Explain the problem, proposed work, acceptance criteria, and priority using
  verified evidence and user impact in this repository.
- Apply reusable ideas to this repository's actual code, configuration, and
  conventions. Another project's policy or implementation is not evidence that
  the same requirement applies here.
- Remove copied project names, issue links, process labels, and release
  assumptions that are unrelated to the requested work.
- Keep relevant technical evidence and source attribution, including actual
  dependencies, integrations, upstream defects, and official documentation.
  Explain the relationship and the work owned by this repository. Apply the
  same local-evidence requirement to explicitly requested comparisons.
- Before creating or editing an issue, search for duplicates and review every
  project name and repository link in the title and body. The issue must be
  understandable without following an unrelated project's issue or policy.
- After saving, fetch the issue again and verify the saved title, body, and
  labels before reporting completion. Apply these checks to issues created
  through the API or CLI as well as through the issue forms.


### Title

Titles for issues, pull requests, and commits follow the **Title Convention** in [`CONTRIBUTING.md`](CONTRIBUTING.md#title-convention), the single source of truth for the format and the allowed types.

### Body

Use the following sections, in order, omitting any that do not apply:

```
## Context
What problem this issue addresses and why now. Note the target release (e.g. vX.Y.Z) here if known.

## Acceptance Checklist
- [ ] Concrete, verifiable items.

## Out of scope
- Items intentionally excluded, with links to the issues that track them.

## References
- Relevant issues, PRs, ADRs, official documentation, and documented dependencies or integrations.
```

### Labels

- Apply at least one type label: `bug`, `enhancement`, `documentation`, or `chore` (`ci`, `test`, `question` where they fit).
- Every new issue gets `needs-triage` (issue forms and the `Triage new issues` workflow add it automatically; add it yourself when creating issues programmatically). **Do not remove it until validity, duplicate checks, repository scope, type, priority, and size have all been confirmed and saved.**
- Priority uses exactly one of the exact GitHub label names `priority: critical` / `priority: high` / `priority: medium` / `priority: low` (lowercase values; a space follows the colon). Never write P0/P1/P2.
  - `critical` — fix now: security issue, data loss, broken released package, or blocked release pipeline.
  - `high` — address before the next planned release; serious impact or no reasonable workaround.
  - `medium` — normal planned work; a workaround exists or scope is limited.
  - `low` — opportunistic polish or non-urgent improvement.
- Priority may be provisional while `needs-triage` is present. An external contributor without label permissions should describe urgency in the issue body.
- Give each actionable issue exactly one effort label using the **exact case-sensitive GitHub label names**: `size: XS` (up to half a working day), `size: S` (about one working day), `size: M` (about two to three working days), `size: L` (about four to five working days), or `size: XL` (more than five working days). Include implementation, tests, CI and docs in the estimate. These are estimates, not deadlines. Split independent or multi-concern work into focused repository-specific issues; retain `size: XL` only when a cohesive task cannot reasonably be split and its scope is justified. For umbrella trackers, size the tracking work itself, not the sum of child issues, and size each child independently.
- Completing triage is a deliberate maintainer/authorized-agent action: verify the issue is actionable, not a duplicate, has its appropriate type/area labels, **one `priority:*` and one `size:*` label**; then remove `needs-triage`. If any decision remains uncertain, leave `needs-triage` and record what is missing. Do not remove it merely because a priority label was assigned.
- Each triage pass must re-evaluate the **entire open-issue backlog in this repository** (not just the newest issue) for relative urgency, impact, release blockers, dependencies, duplication, and effort. Keep priorities consistent, adjust stale priority/size labels when evidence or scope changes, and state which issues should be addressed first. Reapply `needs-triage` if a material scope change invalidates a prior assessment.
- Use exactly one label from the four `priority: ...` values and one from the five `size: ...` values per actionable open issue. Priority is based on impact/urgency, not size; a small security defect may outrank a large enhancement. Do not introduce a separate ranking, project board, or shared cross-repository tracker.
- Add `area:*` labels when they exist in the repository.
- Use `blocker` only when the issue blocks a release.
- There is no work-in-progress label. Open unfinished pull requests as Draft PRs, and link the issue with `Fixes #N` so its in-progress state shows on the issue.

### Umbrella issues

When splitting a large piece of work into focused issues, keep the umbrella open as a tracker that links each child issue with a checkbox; close it once every child is closed or explicitly deferred.

### Issue-creation access

Keep issue creation **open/unrestricted** in this repository (issue tracker enabled, no `interaction-limits`). External bug reports are the only inbound support channel, so restricting issue creation suppresses the signal we most need. Do not enable an interaction limit or restrict issue creation without an explicit, documented reason recorded in an issue first.

## Validation
- `make test`
- `make lint`
- `make typecheck`
- `make build`

## Release Process

Three tools, one job each. Nothing else participates.

| Tool | Owns |
|---|---|
| **Release Please** | version decision, `__version__`, `CHANGELOG.md`, Release PR, tag, GitHub Release |
| **GitHub Actions** | verification, real-Azure e2e, PyPI publish |
| **Hatch** | building the Python package (reads `__version__` from `src/azure_functions_logging/__init__.py`) |

- **Do NOT manually edit version strings, `CHANGELOG.md`, `.release-please-manifest.json`, or tags.** Release Please owns all of them. The public-API test reads `__version__` against `importlib.metadata.version(...)`, so no test changes are needed when bumping.
- Releases are driven by **Conventional Commits** on `main`, but only **user-facing** types cut one: `fix:` → patch, `perf:`/`revert:` → patch, `feat:` → minor, `feat!:`/`fix!:`/`BREAKING CHANGE:` → breaking. While this package is pre-1.0, `bump-minor-pre-major` keeps a breaking change on the `0.x` line.
- **`docs:`, `ci:`, `chore:`, `test:`, `build:`, `style:` and `refactor:` do not cut a release.** They are marked `"hidden": true` in `release-please-config.json`, which keeps them out of `CHANGELOG.md`; when a batch of commits contains nothing else, the release notes render empty and Release Please logs `No user facing commits found since <sha> - skipping` and opens no Release PR. Merging such a PR and seeing no version change is the intended outcome, not a broken pipeline. A breaking change still releases whatever its type is.
- There are **no release Makefile targets**. `make release-*`, `make changelog`, `make tag-release`, and `make publish-pypi` were deleted; a local `hatch publish` would have skipped every gate below.

### Flow

```
feat:/fix: PR merged into main
        |
  Release Please  ->  Release PR (version + CHANGELOG)
        |  maintainer reviews and merges
  tag vX.Y.Z + GitHub Release
        |
  publish-pypi.yml  (started by the tag)
        build -> lib-tests -> cookbook-smoke -> cookbook-host-smoke
              -> azure-e2e -> PyPI
```

1. Merge Conventional-Commit PRs into `main`. Release Please keeps an open **Release PR** showing exactly what the next release would be.
2. Merging that Release PR is the act of cutting a release.
3. Release Please tags the release commit and publishes the GitHub Release. The tag starts `publish-pypi.yml`.
4. Every verification tier runs in that one workflow. PyPI upload happens only if all of them pass.
5. Update `docs/changelog.md` separately if needed. It holds hand-maintained version history and migration notes, and Release Please does not touch it.

**Certification is an in-chain gate.** `azure-e2e` deploys to real Azure and runs the live e2e suite at the same ref being published, so it covers the exact published commit by construction. There is no separate certification step to dispatch, and no cross-run SHA or freshness matching to get wrong.

**`RELEASE_PLEASE_TOKEN` is load-bearing.** It is a fine-grained PAT stored as a repository secret. The default `GITHUB_TOKEN` cannot trigger other workflows, which would leave the Release PR without the required status checks — permanently unmergeable — and would stop the tag from starting `publish-pypi.yml`. The PAT grants repository write only; PyPI upload uses OIDC Trusted Publishing and cannot be reached with it. **Fine-grained PATs expire**: when it does, no Release PR appears. Regenerate it and update the secret before the expiry date.

### Tiered runtime verification (what gates a release)

Every tier runs inside `publish-pypi.yml` on the tag, and **all of them gate the upload**:

| Tier | Catches |
| --- | --- |
| `build` | tag/`__version__` mismatch; produces the one artifact that is later uploaded |
| `lib-tests` | library unit regressions |
| `cookbook-smoke` | downstream import/registration drift |
| `cookbook-host-smoke` | package-specific runtime and host-boot compatibility: installs the candidate wheel, collects only the cookbook's existing `package_logging` E2E selection, and exercises logging output/correlation through a real `func` host + Azurite. The pinned cookbook SHA, tool versions, dependency resolution, wheel digest, selection, JUnit output, and sanitized host diagnostics make the attempt reproducible. |
| `azure-e2e` | cloud-only drift — deploys to real Azure, runs the live e2e suite, uploads an `azure-cert` record |
| `publish` | uploads the exact artifact `build` produced; it never rebuilds |

### Recovery
- **Any gate failed.** Nothing was uploaded, so the version is still free. `workflow_dispatch` takes no inputs; the workflow reads the version to verify from `github.ref_name`, so retrying the *same unchanged* tagged candidate (a flaky Azure deploy, a PyPI outage, a runner hiccup) means dispatching with the existing tag itself as the ref: `gh workflow run publish-pypi.yml --ref vX.Y.Z` (not `--ref main` with a `tag=` input — that input does not exist). If the failure instead requires a code or workflow correction, fix forward on `main` and let the next Release PR cut a new version — never move or reuse a tag to make a changed commit appear to be the same release candidate.
- **A tag exists but was never published.** A valid resting state. Re-run publish, or abandon the version and let the next release take the following number.
- **Release PR stopped appearing.** First check that `RELEASE_PLEASE_TOKEN` has not expired. Then check for a stale `autorelease: pending` label on an already-merged Release PR — Release Please treats that as a release still in flight and will not open another. This failure is silent: the workflow still reports success.
- **Break-glass (automation unavailable).** Bump `__version__`, match `.release-please-manifest.json`, commit, tag, and push. The tag starts the same gated workflow — never bypass it.

### Post-release verification

**Verify the release against the dogfood cookbook.**

Once **Publish to PyPI** succeeds, confirm the downstream consumer still passes on the freshly published version:
- In [`azure-functions-cookbook-python`](https://github.com/yeongseon/azure-functions-cookbook-python), upgrade to the new release (`hatch run pip install -U "azure-functions-logging>=X.Y,<1"`) and run `make test`.
- Treat any new `RuntimeWarning`/`DeprecationWarning` surfaced by this library during the cookbook run as a release-blocking signal — decorator-order and API-drift problems are reported as warnings, so a clean run (zero warnings from this package) is part of the release gate.
- If the cookbook pins a lower bound (`azure-functions-logging>=X.Y,<1`), bump it to the new minor in the same verification PR so examples are tested against the version they advertise.
- A release is **not** considered done until the cookbook passes on the published version.

## Golden Commands

Use Makefile entry points only. Do not bypass the Makefile in CI or contributor guidance.

| Purpose | Command |
| --- | --- |
| Environment setup | `make install` |
| Format code | `make format` |
| Lint | `make lint` |
| Type check | `make typecheck` |
| Tests | `make test` |
| Clean | `make clean` |

## Design Constraints

- The root logger's handlers and level are never modified in Azure mode; the library may add package-owned filters (e.g. `ContextFilter`) to existing handlers and to the root logger for late-handler coverage.
- In Azure environments, behavior is safe by default — no forced colors, no excessive handler additions, no interference with the worker's `AsyncLoggingHandler`.
- Context injection failures never cause application failures.
- The API surface stays as close to standard `logging` as possible.
- `azure-functions>=1.21.0` is a required runtime dependency; OpenTelemetry remains an optional `[otel]` extra, imported only when `activate_trace_context=True` is used.

## Commit Rules

Titles for issues, pull requests, and commits follow the **Title Convention** in [`CONTRIBUTING.md`](CONTRIBUTING.md#title-convention), the single source of truth for the format and the allowed types.

## Agent Rules

When using AI-assisted development:

- Prefer small, reviewable changes.
- Do not guess about behavior that can be verified.
- Follow this repository's established structure, scope, and contribution rules.
- Update docs, examples, and tests together when behavior changes.

## Final Rule

If it is not automated, it will drift.
If it is not documented, it is not a stable rule.

## Merge Policy

- `main` requires a pull request, every required status check green, and all conversations resolved. It requires **zero approving reviews**: `yeongseon` is the only account with push access and GitHub forbids approving your own PR, so a required approval could only ever be met by an administrator bypass. The required checks are what guard `main`.
- **Never use `gh pr merge --admin` to skip a failing or pending required check.**
- Review is still expected, just not enforced. An AI review (`COMMENTED`) is not an approval.
- **Dependabot:** `pip` patch/minor updates auto-merge on green CI. `github-actions` updates never auto-merge — confirm each pinned SHA matches its claimed tag (`git ls-remote --tags <repo>`, compare against the dereferenced `^{}` commit) before merging. `dependabot-automerge.yml` enforces the split.
- If a second maintainer ever gets push access, raise the approval count back to 1.

## Branch Hygiene

- Merged PR branches are deleted automatically ("Automatically delete head branches" is enabled on this repository); keep that setting on.
- When merging from the CLI, always pass `--delete-branch` (e.g. `gh pr merge --squash --delete-branch`) so the head branch is removed.
- Never delete `main` or `gh-pages`, and never delete a branch that still has an open PR.
- Run `git fetch -p` periodically to prune stale local tracking refs.
