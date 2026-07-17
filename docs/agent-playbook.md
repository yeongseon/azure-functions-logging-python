# Agent Playbook

## Source Of Truth
- `AGENT.md` for repository-wide engineering and agent rules.
- `README.md` for installation, quick start, and CLI examples.
- `CONTRIBUTING.md` for branch, commit, and release workflow.
- `pyproject.toml` and `Makefile` for supported commands.

## Repository Map
- `src/azure_functions_logging/` package code.
- `tests/` structured logging and redaction coverage.
- `examples/` example logging configurations.
- `docs/` documentation site content.

## Change Workflow
1. Confirm whether the change affects logging API, redaction behavior, configuration, or docs only.
2. Update examples when they are used as public contract material.
3. Keep tests and docs in lockstep for public behavior changes.
4. When changing the public API or `README.md`, propagate the same updates to the i18n READMEs (`README.ja.md`, `README.ko.md`, `README.zh-CN.md`) and to `docs/api.md` in the same PR.
5. Do not broaden supported Python versions or dependency ranges casually.

## Validation
- `make test`
- `make lint`
- `make typecheck`
- `make security`
- `make build`
