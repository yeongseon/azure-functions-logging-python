# Development

This guide explains how to set up a development environment for `azure-functions-logging`.

## Prerequisites

- Python 3.10 or higher
- Git
- Make (for running development commands)

## Getting Started

1. Clone the repository:

   ```bash
   git clone https://github.com/yeongseon/azure-functions-logging-python.git
   cd azure-functions-logging-python
   ```

2. Install the package in editable mode with development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

3. Install pre-commit hooks:

   ```bash
   pre-commit install
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
| `make test` | Run test suite | pytest |
| `make cov` | Run tests with coverage report | pytest-cov |
| `make security` | Security vulnerability scan | bandit |
| `make check-all` | Run all checks (full local gate) | All of the above |

### Running Individual Commands

```bash
make format      # Fix formatting issues
make style       # Check for lint violations
make typecheck   # Check types
make test        # Run all tests
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
hatch run lint:all       # Run all linting checks
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
make test          # Run all tests
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

1. Runs `make check-all` (format, lint, typecheck, security, tests)
2. Tests across the Python version matrix: 3.10, 3.11, 3.12, 3.13, 3.14
3. Generates coverage report
4. Uploads coverage to Codecov

Pull requests must pass all CI checks before merging.

## Building and Publishing

Build the package:

```bash
hatch build
```

The output goes to `dist/`. Publishing to PyPI is handled by the release workflow (triggered by version tags).
