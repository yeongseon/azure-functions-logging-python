# Agent Playbook

## Source Of Truth
- `AGENTS.md` for repository-wide engineering and agent rules.
- `README.md` for installation, quick start, and CLI examples.
- `CONTRIBUTING.md` for branch, commit, and release workflow.
- `pyproject.toml` and `Makefile` for supported commands.

## Repository Map
- `src/azure_functions_logging/` package code.
- `tests/` structured logging and redaction coverage.
- `examples/` example logging configurations.
- `docs/` documentation site content.

## Issue Authoring

Follow [Repository scope](https://github.com/yeongseon/azure-functions-logging-python/blob/main/AGENTS.md#repository-scope)
before creating or editing an issue and verify the saved title, body, and labels afterwards.
This also applies when using the API or CLI.

## Change Workflow
1. Confirm whether the change affects logging API, redaction behavior, configuration, or docs only.
2. Update examples when they are used as public contract material.
3. Keep tests and docs in lockstep for public behavior changes.
4. When changing the public API or `README.md`, update `docs/api.md` in the same PR. Propagate the same changes to the i18n READMEs (`README.ja.md`, `README.ko.md`, `README.zh-CN.md`) opportunistically — translation sync is best-effort and never blocks a PR (see `AGENTS.md`'s Documentation & Translations policy).
5. Do not broaden supported Python versions or dependency ranges casually.

## Validation
- `make test`
- `make lint`
- `make typecheck`
- `make security`
- `make build`

## Review Evidence

Follow [`docs/review-evidence-policy.md`](review-evidence-policy.md) for recording review
source/SHA, findings disposition, and R3 human-authorization notes in the PR body. This is
advisory, not a required check — it does not change the zero-native-approval merge policy (#459)
or the required CI contexts in `AGENTS.md`.
