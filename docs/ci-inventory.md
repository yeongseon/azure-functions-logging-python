# CI workflow inventory

Current inventory of `.github/workflows/` (generated from the workflow files, then
classified by hand). `tests/test_workflow_inventory.py` fails when a workflow file is
added or removed without updating this page, and when a required branch-protection
check stops being reported by a workflow that runs on pull requests.

## Required branch-protection checks

Branch protection on `main` requires exactly these contexts (read from the repository
settings, not inferred): `bandit`, `semgrep`, `Analyze`, `PR title`, `ci-required`.
`ci-required` is the single aggregate for `ci-test.yml`; it reads every dependency's
result and always reports, so changing the test matrix cannot leave a required name
pending. Renaming any of these jobs requires migrating branch protection first.

<!-- required-checks:bandit,semgrep,Analyze,PR title,ci-required -->

## Workflows

<!-- workflow-inventory:start -->
| File | Purpose | Trigger | Class | Required check |
| --- | --- | --- | --- | --- |
| `ci-test.yml` | Lint/type, unit matrix 3.11-3.14, minimum dependencies, wheel smoke, real `func` host smoke, docs build + link lint + Mermaid render | PR, push | CI | `ci-required` |
| `codeql.yml` | CodeQL `security-extended` | PR, push, weekly | Security | `Analyze` |
| `security.yml` | Bandit and Semgrep with scope/evidence checks | PR, push, weekly | Security | `bandit`, `semgrep` |
| `pr-title.yml` | Title Convention check | PR | CI | `PR title` |
| `stale.yml` | Stale issues/branches, branch-name validation | daily, PR, issues | Maintenance | - |
| `triage.yml` | Label new issues | issues | Maintenance | - |
| `dependabot-automerge.yml` | Auto-merge pip patch/minor Dependabot PRs on green CI | `pull_request_target` | Maintenance | - |
| `release-please.yml` | Release PR, tag, GitHub Release notes, tag verification | push to `main`, manual | Release | - |
| `publish-pypi.yml` | Build, library tests, cookbook smoke, host smoke, Azure certification, runtime audit, PyPI publish | `v*` tags, manual | Release | - |
| `e2e-azure.yml` | Real Azure deploy + e2e (called by `publish-pypi.yml`) | `workflow_call`, manual | Azure e2e | - |
| `release-audit.yml` | Audit release history | weekly, manual | Release | - |
| `dependency-audit.yml` | `pip-audit` of runtime and development dependencies (reporting only) | weekly, manual | Security | - |
| `sbom.yml` | Generate SBOM | weekly, manual | Security | - |
| `otel-nightly.yml` | Run OTel-focused tests against the newest `opentelemetry-*` | daily, manual | Canary | - |
| `e2e-host-matrix.yml` | Host-boot smoke across Core Tools versions | weekly, manual | Canary | - |
| `doc-link-integrity.yml` | Network verification of external doc links | weekly, manual | Docs | - |
| `maintenance.yml` | Weekly re-run of lint + Bandit on `main` to catch unpinned-tool drift | weekly, manual | Maintenance | - |
<!-- workflow-inventory:end -->

## Duplicates found and disposition

| Item | Finding | Disposition |
| --- | --- | --- |
| `docs.yml` ("Docs (strict build check)") | Manual-only. Its single step, `mkdocs build --strict`, is a strict subset of the `docs-check` job in `ci-test.yml` (strict build + link lint + Mermaid render + doc tests), which runs on every docs change and is part of `ci-required`. | **Removed.** No required context referenced it. |
| `mermaid-lint.yml` | Manual-only. Runs `scripts/render_mermaid.py`, which `docs-check` in `ci-test.yml` also runs. | **Removed.** Same coverage remains in `ci-required`. |
| `maintenance.yml` typecheck step | `hatch run lint` already runs `style` and `typecheck`; the extra `hatch run typecheck` ran mypy twice. | **Trimmed** to `hatch run lint`. |
| `maintenance.yml` vs `security.yml`/`ci-test.yml` | Scheduled re-run of the same lint/Bandit on an unchanged `main`; it is the only weekly drift signal for unpinned tool versions. | Retained (gate unchanged); revisit when tool versions are pinned. |
| `tests/test_workflow_pin_hygiene.py` vs `tools/lint_workflow_pins.py` in `quality` | The pin lint runs in the `quality` job and again inside the pytest matrix. | Retained: removing a test would weaken coverage; they exercise the lint's behavior (fixtures), not only the repo state. |
| `dependency-audit.yml` vs `publish-pypi.yml` `runtime-dependency-audit` | Same tool, different scope and blocking behavior (reporting vs release gate). | Retained: not duplicates. |
| `publish-pypi.yml` `lib-tests` vs `ci-test.yml` `test` | The release gate re-runs the suite on the tagged ref (coverage gate). | Retained: release verification must run at the published ref. |

## Before / after

| Metric | Before | After |
| --- | --- | --- |
| Workflow files | 19 | 17 |
| Required branch-protection contexts | 5 | 5 (unchanged names) |
| Jobs gating PRs | unchanged | unchanged |
| Manual-only duplicate jobs | 2 | 0 |
| mypy invocations in `maintenance.yml` | 2 | 1 |

Measured from recent successful runs (`gh run list`, median wall-clock): `ci-test.yml` 87 s,
`security.yml` 51 s, `codeql.yml` 63 s, `docs.yml` 48 s, `mermaid-lint.yml` 52 s,
`maintenance.yml` 50 s. The removed workflows were manual-only, so PR feedback latency
and PR runner minutes are unchanged; the saving is two dispatchable workflows and one
duplicated mypy run per weekly maintenance job. No skipped job counts as a pass:
`ci-required` still requires the exact expected result for every dependency.

Not changed in this pass (needs run evidence): consolidating the Python matrix, merging
`sbom.yml` into another scheduled job, and workflow-name based release checks.
