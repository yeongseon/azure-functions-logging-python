# Development

This guide explains how to set up a development environment for `azure-functions-logging`.

## Prerequisites

- Python 3.11-3.14 (`>=3.11,<3.15`)
- Git
- Make (for running development commands)
- Hatch installed once in an isolated tool environment
- Functions Core Tools (`func`) and Azurite for integration/verify only

## Getting Started

1. Clone the repository:

   ```bash
   git clone https://github.com/yeongseon/azure-functions-logging-python.git
   cd azure-functions-logging-python
   ```

2. Install the package in editable mode with development dependencies:

   ```bash
    make install
   ```

3. Install pre-commit hooks:

   ```bash
    make precommit-install
   ```

4. Verify everything works:

   ```bash
   make check-all
   ```

## Project Structure

```
azure-functions-logging/
+-- src/azure_functions_logging/   # Library source code
|   +-- __init__.py                # Public API (setup_logging, get_logger, inject_context)
|   +-- _setup.py                  # Logging system configuration
|   +-- _logger.py                 # FunctionLogger implementation
|   +-- _context.py                # contextvars and ContextFilter
|   +-- _json_formatter.py         # JsonFormatter (NDJSON output)
|   +-- _formatter.py              # ColorFormatter (terminal output)
|   +-- _host_config.py            # host.json conflict detection
|   +-- py.typed                   # PEP 561 type checking marker
+-- tests/                         # Test suite (pytest)
|   +-- test_context.py          # Context injection tests
|   +-- test_formatter.py        # ColorFormatter tests
|   +-- test_host_config.py      # host.json conflict detection tests
|   +-- test_integration.py      # End-to-end integration tests
|   +-- test_json_formatter.py   # JsonFormatter tests
|   +-- test_logger.py           # FunctionLogger wrapper tests
|   +-- test_setup.py            # Logging setup tests
+-- docs/                          # Documentation (MkDocs)
+-- pyproject.toml                 # Build configuration (hatch)
+-- Makefile                       # Development task automation
+-- mkdocs.yml                     # Documentation site config
```

## Development Commands

All development tasks are automated via `Makefile` targets:

| Command | Description | Tools Used |
| ------- | ----------- | ---------- |
| `make format` | Auto-format code | ruff |
| `make style` | Lint for code quality issues | ruff |
| `make typecheck` | Static type checking | mypy (strict) |
| `make lint` | Run both `style` and `typecheck` | ruff, mypy |
| `make test` | Offline unit/mock suite, all privacy regressions, coverage >=95% | pytest |
| `make cov` | Run tests with coverage report | pytest-cov |
| `make security` | Security vulnerability scan | bandit |
| `make install` / `make install-ci` | Isolated local setup / CI-selected interpreter setup | Hatch / selected Python |
| `make doctor` | Read-only prerequisite check; missing required tools fail | canonical runner |
| `make format-check` | Non-mutating formatting check | Ruff |
| `make check` | Lint, format, strict mypy once, security, workflow/doc-link policies | non-mutating |
| `make integration` | Separate OTel, decorated-host and correlation-host lanes; private Azurite | managed processes |
| `make verify` | Check + test + integration + wheel smoke + strict docs | full local gate |
| `make check-all` | Exact alias of verify | full local gate |
| `make e2e-azure` | Explicit deployed candidate and App Insights ingestion | no provisioning |
| `make report` | Render saved JSON, never rerun tests | canonical runner |
| `make clean` | Generated artifacts only, preserve environments/shared data | allowlisted cleanup |
| `make clean-all` | Deep cleanup including bytecode and local `.venv` | maintenance |

Other targets (`lint`, `style`, `typecheck`, `security`, `cov`, `bench`, `build`,
`wheel-smoke`, `docs`, `otel`, `host-smoke`, `host-matrix`, workflow/link lints)
are partial/focused. `e2e-local` checks an already-running local app, not Azure.
Routine commands never upgrade pip or reinstall Hatch. CI uses `make install-ci`
and the canonical runner on its selected Python/SDK/OTel versions, never the
Python 3.11 Hatch default. Quality checks include Mermaid rendering via `mmdc`
and its Chromium installation, using temporary output only.

### Evidence and certification

Gitignored `test-results/` holds separate `test/`, `otel/`, `host-smoke/`,
`host-matrix/`, `integration/`, `verify/`, and `azure-e2e/` summaries. Unit evidence
includes JUnit and coverage XML; integration copies JUnit/logs while retaining each
lane's summary; verify adds `lanes.json` and `environment.json`. Every summary has
schema version, command, selected/passed/failed/skipped counts, status, exit code
and supporting paths. Actual interpreter/SDK/service versions are recorded.
Secrets are masked before console/Job Summary publication and artifact upload.

PASS requires execution; failures/timeouts are FAIL; missing prerequisites,
zero/all-skipped tests and required skipped assertions are INCOMPLETE/non-zero.
NOT_APPLICABLE is only a capability not requested/supported, never missing tools.
Local host and OTel instrumentation cannot certify cloud ingestion. A skipped
App Insights assertion is listed in `cloud_tests_not_run`; `cloud_monitor` is
NOT_APPLICABLE for local runs and INCOMPLETE for required Azure certification.
Deployed-version matching is separately derived from its JUnit assertion.

`make e2e-azure` requires `E2E_BASE_URL`, `E2E_EXPECTED_VERSION`, `APPINSIGHTS_NAME`,
`E2E_RESOURCE_GROUP` and authenticated `az`. It never provisions. Host lanes use
private temporary storage, unique ephemeral ports, bounded readiness, and owned
process-group cleanup. See the repository CONTRIBUTING.md for the full contract.

### Running Individual Commands

```bash
make format      # Fix formatting issues
make style       # Check for lint violations
make typecheck   # Check types
make test        # Offline suite only
make cov         # Run tests with coverage
make security    # Run security scan
make check-all   # Run everything
```

## Environment Management

### Using pip (simple)

```bash
pip install -e ".[dev]"
```

### Using Hatch (recommended)

The project uses [Hatch](https://hatch.pypa.io/) as its build system and environment manager. Hatch handles virtual environments and dependency isolation automatically:

```bash
hatch run test           # Run tests in managed environment
hatch run lint           # Focused lint and type checks
hatch run cov            # Run tests with coverage
```

Hatch creates isolated environments for each task, ensuring clean dependency resolution.

## Making Changes

### Workflow

1. Create a feature branch:

   ```bash
   git checkout -b feat/my-feature
   ```

2. Make changes in `src/azure_functions_logging/`

3. Add or update tests in `tests/`

4. Run checks:

   ```bash
   make check-all
   ```

5. Commit using conventional commit format:

   ```bash
   git commit -m "feat: add new feature"
   ```

### Module Conventions

- Private modules use underscore prefix: `_setup.py`, `_logger.py`, `_context.py`
- Public API is exported from `__init__.py`
- Each module has a single responsibility
- All public functions have complete type annotations

### Adding a New Feature

1. Implement the feature in the appropriate module (or create a new private module)
2. Export any public API from `__init__.py` and add to `__all__`
3. Write tests covering the new functionality
4. Update the API reference in `docs/api.md`
5. Update the usage guide in `docs/usage.md` if the feature is user-facing

### Fixing a Bug

1. Write a failing test that reproduces the bug
2. Fix the bug in the source code
3. Verify the test passes
4. Update documentation if the fix changes behavior

## Testing

See the [Testing](testing.md) guide for detailed information on the test suite.

Quick reference:

```bash
make test          # Offline suite only
make cov           # Run with coverage report
pytest tests/test_formatter.py   # Run specific test file
pytest -k "test_json"            # Run tests matching pattern
```

## Type Checking

The project uses mypy in strict mode. All code must pass type checking:

```bash
make typecheck
```

Key rules:

- All function parameters and return types must be annotated
- No `Any` types except where required for compatibility
- No `# type: ignore` without a comment explaining why
- `py.typed` marker is included for PEP 561 compliance

## Code Formatting

Code is auto-formatted with ruff:

```bash
make format
```

This is non-destructive -- run it frequently during development. The pre-commit hook runs formatting automatically before each commit.

## Security Scanning

The project uses bandit for security analysis:

```bash
make security
```

Bandit checks for common security issues in Python code (hardcoded passwords, SQL injection, unsafe deserialization, etc.).

## Pre-commit Hooks

Pre-commit hooks run automatically before each commit:

```bash
pre-commit install    # Install hooks (one-time setup)
pre-commit run --all  # Run hooks on all files manually
```

The hooks check formatting, linting, and type safety. If a hook fails, the commit is rejected until the issue is fixed.

## CI Pipeline

CI runs on every push and pull request via GitHub Actions. The pipeline:

1. Runs `make check` (non-mutating format/lint/types/security/policies)
2. Tests across the Python version matrix: 3.11, 3.12, 3.13, 3.14
3. Generates coverage report
4. Uploads coverage to Codecov
5. Runs the same canonical managed host runner and preserves wheel/minimum-dependency gates
6. Uploads `test-results/**` even on failure and appends the same counts/status to Job Summary

Pull requests must pass all CI checks before merging.

## Building and Publishing

Build the package:

```bash
hatch build
```

The output goes to `dist/`. Publishing to PyPI is handled by the release workflow (triggered by version tags).
