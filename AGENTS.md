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
- When a change touches `README.md` or any English documentation, update the translated READMEs (`README.ko.md`, `README.ja.md`, `README.zh-CN.md`) **in the same PR** so translations never drift from the English source.
- This applies to any code change that alters documented behavior, CLI output, or the ecosystem/package table — not just direct edits to prose.
- If a full translation cannot land in the same PR, add a short "translation pending" note to the affected translated file and open a tracking issue before merging.

## Issue Conventions

Follow these conventions when opening issues so the backlog stays consistent with sibling DX Toolkit repositories.

### Title

- Use Conventional Commit prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`, `build:`, `perf:`.
- Add a scope qualifier when it narrows the area: `feat(json):`, `docs(context):`, `refactor(logger):`.
- Keep the title imperative, under ~80 characters, no trailing period.
- Do **not** put `[P0]` / `[P1]` / `[P2]` (or any priority marker) in the title — priority is tracked with a `priority:p0` / `priority:p1` / `priority:p2` label.

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
- Apply exactly one `priority:p0` / `priority:p1` / `priority:p2` label to record priority (replaces the old `## Priority` body line).
- Add `area:*` labels when they exist in the repository.
- Use `blocker` only when the issue blocks a release.

### Umbrella issues

When splitting a large piece of work into focused issues, keep the umbrella open as a tracker that links each child issue with a checkbox; close it once every child is closed or explicitly deferred.

## Validation
- `make test`
- `make lint`
- `make typecheck`
- `make build`

## Release Process
- Version is managed via `hatch` (dynamic from `src/azure_functions_logging/__init__.py`).
- **Do NOT manually edit version strings.** Use the Makefile targets below. The public-API test reads `__version__` against `importlib.metadata.version(...)`, so no test changes are needed when bumping.

### Commands
- `make release-patch` — bump patch version, update changelog, tag, and push
- `make release-minor` — bump minor version, update changelog, tag, and push
- `make release-major` — bump major version, update changelog, tag, and push
- `make release VERSION=x.y.z` — set explicit version, update changelog, tag, and push
- `make tag-release VERSION=x.y.z` — create and push an annotated tag (used internally by release targets)

### Flow
1. `make release-patch` (or `-minor` / `-major`) on `main`
2. This runs: `hatch version` → `git commit` → `make changelog` → `git commit` → `git tag` → `git push`
3. Tag push triggers **Publish to PyPI** GitHub Actions workflow automatically.
4. Update `docs/changelog.md` separately if needed (different format from `CHANGELOG.md`).
5. **Verify the release against the dogfood cookbook.** Once **Publish to PyPI** succeeds, confirm the downstream consumer still passes on the freshly published version:
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

Use Conventional Commits:

```text
<type>: <short imperative summary>
```

Allowed types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`

## Agent Rules

When using AI-assisted development:

- Prefer small, reviewable changes.
- Do not guess about behavior that can be verified.
- Keep repository structure aligned with sibling repositories.
- Update docs, examples, and tests together when behavior changes.

## Final Rule

If it is not automated, it will drift.
If it is not documented, it is not a stable rule.

## Branch Hygiene

- Merged PR branches are deleted automatically ("Automatically delete head branches" is enabled on this repository); keep that setting on.
- When merging from the CLI, always pass `--delete-branch` (e.g. `gh pr merge --squash --delete-branch`) so the head branch is removed.
- Never delete `main` or `gh-pages`, and never delete a branch that still has an open PR.
- Run `git fetch -p` periodically to prune stale local tracking refs.
