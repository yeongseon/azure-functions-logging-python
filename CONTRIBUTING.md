# Contributing Guide

We welcome contributions to the `azure-functions-logging` project.

## Branch Strategy

Use GitHub Flow and branch from `main`.

Recommended branch prefixes:

- `feat/` for new features
- `fix/` for bug fixes
- `docs/` for documentation-only changes
- `chore/` for tooling and maintenance
- `ci/` for workflow updates

## Development Workflow

1. Create a branch from `main`.
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feat/your-feature-name
   ```
2. Write code and tests.
3. Run the local quality gate.
   ```bash
   make check-all
   ```
4. Push and create a pull request.
   ```bash
   git push origin feat/your-feature-name
   ```

## Local development quickstart

Install Hatch once in an isolated tool environment. The default Hatch environment
requires Python 3.11; CI selects Python 3.11–3.14 explicitly. `make install` creates
the isolated dev/docs environment and installs local hooks. Routine commands never
upgrade pip, reinstall Hatch, or change the global interpreter. Offline quality and
unit checks need no services; full local verification requires `func` and `azurite`
on PATH. Docker and an Azure account are not needed locally.

```bash
git clone https://github.com/yeongseon/azure-functions-logging-python.git
cd azure-functions-logging-python
make install
```

Run the standard verification commands from the repository root:

```bash
make test
make check
make verify
```

## Project Commands

| Command | Contract |
| --- | --- |
| `make install` | Isolated Hatch development/docs environment and local hooks |
| `make install-ci` | Install extras into CI's explicitly selected `PYTHON` |
| `make doctor` | Read-only prerequisites; fail non-zero for missing required tools |
| `make format` / `make format-check` | Mutating Ruff formatting / non-mutating check |
| `make check` | Ruff lint/format, strict mypy once, Bandit, workflow/doc-link policies and Mermaid rendering |
| `make test` | Fully offline unit/mock suite, all privacy/redaction regressions, coverage >=95% |
| `make integration` | Separate OTel instrumentation, decorated real-host and correlation host lanes; managed private Azurite |
| `make verify` | Always check + test + integration + installed wheel smoke + strict docs |
| `make e2e-azure` | Explicit existing deployment and actual App Insights ingestion certification; never provisions |
| `make report` | Render saved JSON only, without running tests |
| `make clean` | Generated artifacts only; preserve environments and shared storage |

`make check-all` is an exact backward-compatible alias of `make verify`.
`clean-all` retains historical deep cleanup: artifacts, bytecode and local `.venv`.
Other useful targets are partial/focused: `style`, `lint`, `typecheck`, `security`,
`lint-workflows`, `lint-doc-links`, `cov` (HTML coverage), `bench`, `otel`,
`host-smoke`, `host-matrix`, `build`, `wheel-smoke`, `docs`, `docs-serve`,
`format-check-changed`, and maintenance commands. Quality checks require Mermaid
CLI (`mmdc`) and its Chromium installation; rendering uses temporary output only.

### Verification evidence

```text
test-results/
  test/{junit.xml,coverage.xml,summary.json,environment.json,logs/}
  otel/{junit.xml,summary.json,environment.json,logs/}
  host-smoke/{junit/junit.xml,summary.json,environment.json,logs/}
  host-matrix/{junit/junit.xml,summary.json,environment.json,logs/}
  integration/{summary.json,environment.json,lanes.json,junit/,logs/}
  verify/{summary.json,environment.json,lanes.json,logs/}
  azure-e2e/{summary.json,environment.json,junit.xml,logs/}
```

Each summary records schema version, lane/command, selected/passed/failed/skipped
counts, exit status and supporting paths. Actual Python/runtime/SDK/OTel and live
service versions are captured without dumping environment variables. Credentials,
connection strings (including instrumentation keys/endpoints), authorization,
function keys and SAS are masked in logs, XML, saved JSON, console and Job Summary.
CI runs the same runner on its selected interpreter and uploads `test-results/**`
with `if: always()`; it never routes matrix tests through Hatch's Python 3.11.

- **PASS** requires actual execution and successful required checks.
- **FAIL** means failed tests/checks, non-zero processes or timeouts.
- **INCOMPLETE** means missing prerequisites/evidence, zero tests, all skipped,
  or skipped required live assertions. These runs exit non-zero.
- **NOT_APPLICABLE** is only an explicitly unsupported/not-requested capability,
  never a fallback for missing required tools or cloud assertions.

OTel instrumentation and local Functions-host success do **not** certify Azure
Monitor ingestion. `cloud_monitor` is `NOT_APPLICABLE` locally, with the unrun
App Insights assertion listed in `cloud_tests_not_run`. `e2e-local` targets an
already-running app and permits only that explicitly optional cloud assertion to
skip. A required `azure-e2e` run with that assertion skipped or absent is
`INCOMPLETE`, never PASS—even if HTTP tests passed. Deployed-version matching has
its own status derived from the actual JUnit assertion, not from configuration.

Real Azure requires `E2E_BASE_URL`, `E2E_EXPECTED_VERSION`, `APPINSIGHTS_NAME`,
`E2E_RESOURCE_GROUP`, and an authenticated `az` CLI. The runner never deploys or
provisions; the existing release workflow still owns deployment, exact-ref and
candidate-version records, cleanup, OIDC, and upload of the original built artifact.
Telemetry destination is recorded as configured/redacted, never a connection string.
Host lanes use temporary storage, distinct ephemeral ports and bounded readiness;
only their owned process groups are stopped, including on interruption. Core Tools
may need its extension bundle cached before an offline host run.

## GitHub Actions Pinning

All external `uses:` references in `.github/workflows/` MUST pin to a
full 40-character commit SHA with a trailing comment documenting the
released version or channel. Example:

```yaml
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6
```

This applies to first-party (`actions/*`, `github/*`, `azure/*`) and
third-party Actions alike.

**Rationale.** Mutable tags (including immutable-looking version tags
like `@v6.0.1`) can be retroactively moved by an attacker who gains
write access to the upstream repository. The
[`tj-actions/changed-files` compromise (CVE-2025-30066, March 2025)](https://github.com/advisories/GHSA-mrrh-fwg8-r2c3)
demonstrated this exact failure mode: ~23,000 repositories had their CI
secrets exfiltrated, and only workflows that pinned to a commit SHA were
safe. GitHub's own guidance now identifies SHA pinning as
[the only way to use an Action as an immutable release](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions),
and OpenSSF Scorecard's
[`Pinned-Dependencies` check](https://github.com/ossf/scorecard/blob/main/docs/checks.md#pinned-dependencies)
flags anything weaker as Medium-risk.

Dependabot updates SHA-pinned references on the configured schedule and
keeps the trailing version comment in sync, so the human-readable
context never drifts from the pinned commit.

**Approved exceptions.** The following mutable refs are the only ones
permitted in this repository and are flagged with an inline comment at
the call site:

- Local composite actions (`uses: ./...`) — versioned with the repo.

When adding a new external Action, resolve the SHA with
`git ls-remote <repo-url> 'refs/tags/<tag>^{}'`. The trailing `^{}`
**dereferences** the ref to its target commit; without it, an
*annotated* tag returns the tag-object SHA instead of the commit SHA,
and the tag-object SHA is **not** a valid `uses:` target.

```bash
# Annotated tag — the two forms return *different* SHAs:
git ls-remote https://github.com/Azure/login 'refs/tags/v3.0.0' 'refs/tags/v3.0.0^{}'
# 93381592...   refs/tags/v3.0.0       <- tag object, do NOT pin to this
# 532459ea...   refs/tags/v3.0.0^{}    <- commit, pin to this one

# Lightweight tag — only the non-deref form returns a row, and it is
# already the commit SHA. Always include the `^{}` form anyway so the
# same command works for both tag types:
git ls-remote https://github.com/actions/setup-python 'refs/tags/v6' 'refs/tags/v6^{}'
```

Single-quote the `refs/...^{}` argument so the `{}` and `^` are not
interpreted by your shell (notably zsh with `EXTENDED_GLOB`).

## Example Coverage Policy

Examples are part of the supported API experience and should stay verified.

- Keep one representative example for the minimal structured logging workflow.
- Keep one complex example for advanced configuration and context injection.
- Add or update smoke tests whenever an example changes.
- Prefer lightweight smoke coverage over infrastructure-heavy end-to-end tests.

## Design Guardrails

These are hard API-surface limits, not soft preferences — changing them requires an explicit design discussion in an issue first.

### `setup_logging` complexity ceiling

`setup_logging(...)` today exposes **8 keyword-only parameters** (`level`, `format`, `logger_name`, `functions_formatter`, `host_json_path`, `use_record_factory`, `extra_context_vars`, `activate_trace_context`).

- **No 9th keyword argument.** The next configuration increment must be a **profile/preset** (e.g. a named `profile="..."` bundling related settings), **not** another standalone flag.
- Adding a boolean/flag kwarg is a smell: it multiplies the valid-combination surface and pushes the function toward an untestable configuration matrix.
- If a new behavior seems to need a kwarg, first ask whether it belongs in a preset, in an existing parameter, or in a separate function.

Signature of record: `src/azure_functions_logging/_setup.py`.

### `with_context` parameter ceiling

`with_context(...)` today exposes **5 keyword-only parameters** (`param`, `activate_trace_context`, `strict`, `lifecycle`, `lifecycle_level`).

- **No 6th keyword argument.** Future lifecycle extensions (e.g. sampling, a slow-invocation threshold) must arrive via a **config object / preset** — for example a single `lifecycle=LifecycleConfig(...)` object bundling related settings — **not** as new standalone `lifecycle_*` flags.
- The same reasoning as `setup_logging` applies: each added flag multiplies the valid-combination surface and pushes the decorator toward an untestable configuration matrix.
- If a new behavior seems to need a kwarg, first ask whether it belongs in a preset, in an existing parameter, or in a separate decorator.

Signature of record: `src/azure_functions_logging/_decorator.py`.

## Issue Scope

Follow the [repository-scope rules in AGENTS.md](AGENTS.md#repository-scope)
when opening or editing an issue, including the checks before and after saving.
Explain this repository's problem, evidence, user impact, and completion criteria,
and state why any external project or source is relevant.

## Title Convention

This section is the single source of truth for issue, pull request, and commit titles in this repository. `AGENTS.md`, the pull request template, the issue forms, and the documentation site point here instead of restating the rules.

Issues, pull requests, and the final squash commit on the default branch all use:

```text
type: description
type(scope): description
```

- Write titles in English.
- `type` and `scope` are lowercase. Put exactly one space after the colon.
- `scope` is optional. Add it only when it narrows the area; do not add one just for uniformity.
- `description` states what changes and why, concisely. Start with a lowercase word, but keep the spelling of API names, acronyms, error codes, and proper nouns.
- No trailing period.
- No priority, size, status, or owner markers, and no bracket prefixes such as `[Bug]`, `[Feature]`, or `[WIP]`. Use labels and Draft pull requests instead.
- An issue title may describe the problem; the pull request title describes the change that resolves it. Keep them aligned when they cover the same work, without forcing identical wording when the scope differs.
- Do not put issue numbers in pull request titles. Link issues in the pull request body with `Closes #123` or `Refs #123`.

| type | use for |
|---|---|
| `feat` | a user-facing feature or capability |
| `fix` | a bug fix in product behavior |
| `docs` | documentation only |
| `test` | adding or changing tests |
| `perf` | a performance improvement |
| `refactor` | internal restructuring that keeps external behavior |
| `ci` | CI and automation workflows |
| `build` | build, packaging, and dependency changes |
| `chore` | maintenance that fits none of the above |
| `style` | formatting only, no behavior change |
| `revert` | reverting an earlier change |

A breaking change adds `!` before the colon: `type!: description` or `type(scope)!: description`. Whether a change is breaking, and how it is released, is decided by the Release Process in [AGENTS.md](AGENTS.md), not by the title alone. Release Please reads these titles from the squash commits on `main`: `fix` and `feat` drive the version bump, and the other types only shape the changelog.

Examples:

```text
fix: preserve structured log fields
feat(logging): add an optional context field
docs(readme): clarify the local setup steps
refactor!: rename the public configuration keys
```

Not accepted: `[Bug] crash on save` (bracket prefix, no type), `Fix: crash on save` (uppercase type), `feature: add export` (type not in the table), `fix: crash on save.` (trailing period), `fix: preserve structured log fields (#503)` (the pull request number belongs in the body).

Pull requests are squash-merged and the pull request title becomes the final commit title. GitHub appends the pull request number by itself, so `fix: preserve structured log fields` lands on `main` as `fix: preserve structured log fields (#503)`. Do not write that number into the title yourself — the check rejects a title ending in `(#123)`, because it would be doubled. Link the issue from the pull request body instead, for example `Closes #503`. The **PR title** check validates the format whenever a pull request is opened, edited, reopened, or updated. Individual commits on a branch are not checked.

Issue titles are not enforced. Anyone can open an issue without knowing this convention; maintainers adjust the title during triage.

## Releases

Merging to `main` does not publish a release.

Release Please keeps an open **Release PR** showing what the next version would
be; merging that PR is what cuts the release, and it is what creates the `v*`
tag that starts the publish workflow. Publishing happens only after the release
verification requirements have been satisfied. Contributors never need to bump a
version or tag anything in an ordinary pull request.


See `AGENTS.md` for the maintainer-only release procedure.

## Code of Conduct

Be respectful and inclusive. See our [Code of Conduct](CODE_OF_CONDUCT.md) for details.
