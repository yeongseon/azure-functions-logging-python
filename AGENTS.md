# AGENTS.md

## Purpose
`azure-functions-logging` provides structured JSON logging for Azure Functions Python v2 applications.

## Repository Identity
- Project: `azure-functions-logging`
- Project type: Python library
- Runtime scope: Azure Functions Python v2 programming model
- Minimum supported Python: `3.10`
- Packaging: `pyproject.toml` with Hatch

## Read First
- `README.md`
- `CONTRIBUTING.md`

## Working Rules

### Test Coverage
- Maintain test coverage at **95% or above** for committed changes and PRs.
- Run `hatch run pytest --cov --cov-report=term-missing -q` to verify before submitting changes.
- Any PR that drops coverage below 95% must include additional tests to compensate.
- In Azure/Core Tools mode, `setup_logging()` installs `ContextFilter` on the root logger's existing handlers (and the root logger itself for late-attaching handlers) but never adds new handlers or changes the root level. When `use_record_factory=True`, no `ContextFilter` is attached; context is injected via the global `LogRecordFactory` instead. In standalone local mode, the root logger is configured by default (`logger_name=None`); pass an explicit `logger_name` to avoid modifying the root logger.
- No runtime dependency on `azure-functions` — it is an optional import only.
- Runtime code must remain compatible with Python 3.10+.
- Public APIs must be fully typed.
- Keep documentation examples and tests synchronized with any behavior changes.

### Documentation & Translations
- English (`README.md`) is the **canonical** source of truth for all documentation. Translated READMEs (`README.ko.md`, `README.ja.md`, `README.zh-CN.md`) are **best-effort**, community-maintained, and may lag the English source.
- Translation sync is **not** required in the same PR as an English change, and a PR is **never** blocked by translation drift. Update translations opportunistically; when you do, keep them faithful to the current English source.
- Each translated README carries a staleness banner linking back to the canonical English README. Keep that banner in place so readers always know the translation may be out of date.

## Issue Conventions

Follow these conventions when opening issues so the backlog stays consistent with sibling DX Toolkit repositories.

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
- PRs, ADRs, sibling issues, external docs.
```

### Labels

- Apply at least one of `bug`, `enhancement`, `documentation`, `chore`.
- Apply exactly one priority label. The scale in use is `priority:critical` / `priority:high` / `priority:medium` / `priority:low`; `critical` is reserved for defects that reach package users, such as a broken published artifact or wrong product output.
- Labels are applied by maintainers or authorized triage automation. An external contributor without label permissions should describe urgency in the issue body and leave labelling to triage.
- Add `area:*` labels when they exist in the repository.
- Use `blocker` only when the issue blocks a release.

### Umbrella issues

When splitting a large piece of work into focused issues, keep the umbrella open as a tracker that links each child issue with a checkbox; close it once every child is closed or explicitly deferred.

### Issue-creation access (fleet policy)

Keep issue creation **open/unrestricted** on every public toolkit repository (issue tracker enabled, no `interaction-limits`). External bug reports are the only inbound support channel, so restricting issue creation suppresses the signal we most need. Do not enable an interaction limit or restrict issue creation without an explicit, documented reason recorded in an issue first.

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
| `cookbook-host-smoke` | candidate wheel installs cleanly and a real `func` host + Azurite boots with it present, no cloud. NOTE: the cookbook HTTP examples do not import this package, so this is a host-boot smoke, **not** proof of this package's own runtime behavior (tracked separately) |
| `azure-e2e` | cloud-only drift — deploys to real Azure, runs the live e2e suite, uploads an `azure-cert` record |
| `publish` | uploads the exact artifact `build` produced; it never rebuilds |

### Recovery
- **Any gate failed.** Nothing was uploaded, so the version is still free. Fix the cause and re-run the workflow on the same tag (`gh workflow run publish-pypi.yml --ref main -f tag=vX.Y.Z`), or fix forward on `main` and let the next Release PR cut a new version. Never move or reuse a tag.
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
- No runtime dependency on `azure-functions` — optional import only.

## Commit Rules

Titles for issues, pull requests, and commits follow the **Title Convention** in [`CONTRIBUTING.md`](CONTRIBUTING.md#title-convention), the single source of truth for the format and the allowed types.

## Agent Rules

When using AI-assisted development:

- Prefer small, reviewable changes.
- Do not guess about behavior that can be verified.
- Keep repository structure aligned with sibling repositories.
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
