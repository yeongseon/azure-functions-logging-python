# Contributing

Thank you for your interest in contributing to `azure-functions-logging`. This guide covers the contribution workflow, code standards, and release process.

## Getting Started

1. Fork the repository on GitHub.
2. Clone your fork:

   ```bash
   git clone https://github.com/<your-username>/azure-functions-logging-python.git
   cd azure-functions-logging-python
   ```

3. Install development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

4. Verify your setup:

   ```bash
   make check-all
   ```

See the [Development](development.md) guide for detailed environment setup.

## Contribution Workflow

### 1. Create a Branch

Create a feature branch from `main`:

```bash
git checkout -b feat/my-feature
```

### 2. Make Changes

- Write your code in `src/azure_functions_logging/`
- Add tests in `tests/`
- Update documentation in `docs/` if behavior changes

### 3. Run Checks Locally

Before pushing, run the full local gate:

```bash
make check-all
```

This runs:

| Check | Command |
| ----- | ------- |
| Code formatting | `make format` (ruff) |
| Linting | `make style` (ruff) |
| Type checking | `make typecheck` (mypy) |
| Security scan | `make security` (bandit) |
| Tests | `make test` (pytest) |

### 4. Commit

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

```bash
git commit -m "feat: add JsonFormatter for structured logging"
```

### 5. Push and Open a PR

```bash
git push origin feat/my-feature
```

Open a pull request against the `main` branch with a clear description of what changed and why.

## Commit Message Format

Titles for issues, pull requests, and commits follow the **Title Convention** in [`CONTRIBUTING.md`](https://github.com/yeongseon/azure-functions-logging-python/blob/main/CONTRIBUTING.md#title-convention), the single source of truth for the format and the allowed types.

## Code Standards

### Type Safety

- All public functions and methods must have complete type annotations
- `mypy --strict` must pass without errors
- Do not use `Any` except where necessary for compatibility (e.g., `inject_context(context: Any)`)
- Do not use `# type: ignore` without an inline comment explaining why

### Code Style

- Code is formatted with `ruff` and linted with `ruff`
- Run `make format` to auto-format before committing
- Maximum line length: 100 characters (ruff configured)

### Error Handling

- No empty catch blocks
- Logging-related errors should be caught and handled silently (a logging failure should never crash the application)
- Include actionable context in error messages

### Testing

- All new features must include tests
- All bug fixes must include a regression test
- Tests must pass across the full Python version matrix (3.11-3.14)
- Coverage should not decrease

### Module Conventions

- Private modules are prefixed with underscore (`_setup.py`, `_logger.py`)
- Public API is exported from `__init__.py`
- Each module has a single, clear responsibility
- No circular imports

## Development Commands

| Command | Description |
| ------- | ----------- |
| `make format` | Format code with ruff |
| `make style` | Lint with ruff |
| `make typecheck` | Type check with mypy (strict mode) |
| `make lint` | Run both style and typecheck |
| `make test` | Run tests with pytest |
| `make cov` | Run tests and generate coverage report |
| `make security` | Run bandit security scan |
| `make check-all` | Run full local gate (all of the above) |

## Pre-commit Hooks

Install pre-commit hooks to run checks automatically before each commit:

```bash
pre-commit install
```

The hooks run formatting and linting checks. This catches issues before they reach CI.

## Pull Request Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Update documentation if public behavior changes
- Reference related issues in the PR description (e.g., "Fixes #42")
- Ensure CI passes before requesting review
- Respond to review feedback promptly

## Version Management

Versioning is automated. [Release Please](https://github.com/googleapis/release-please) derives the
next version from Conventional Commits on `main` and maintains all three version writers:

- `src/azure_functions_logging/__init__.py` (`__version__`)
- `CHANGELOG.md`
- `.release-please-manifest.json`

**Do not hand-edit any of them**, and do not create release tags by hand. As a contributor, the only
thing you control is your commit message: `fix:` yields a patch bump, `feat:` a minor one. While the
package is pre-1.0, a breaking change moves to the next minor rather than to `1.0.0`.

## Release Process

Maintainers cut a release by merging the open Release PR (titled `chore(main): release X.Y.Z`), which
Release Please keeps up to date. Merging it tags the commit and publishes the GitHub Release.

Publishing to PyPI is a separate, gated workflow (`publish-pypi.yml`) that runs the full chain before
anything is uploaded:

```
build -> lib-tests -> cookbook-smoke -> cookbook-host-smoke -> azure-e2e -> publish
```

The full procedure, the retired Makefile targets, and the recovery playbook live in the
[Release Process](release_process.md) guide. `AGENTS.md` in the repository root is the canonical
short-form reference.

## Architecture Overview

Before making changes, familiarize yourself with the module structure in the [Architecture](architecture.md) guide. Key points:

- The library uses Python's standard `logging` module exclusively
- Context propagation uses `contextvars` for thread/async safety
- `FunctionLogger` wraps (does not subclass) `logging.Logger`
- Environment detection determines setup behavior (Azure vs. local)
- All public functions are exported from `__init__.py`

## Questions?

Open an issue on [GitHub](https://github.com/yeongseon/azure-functions-logging-python/issues).
