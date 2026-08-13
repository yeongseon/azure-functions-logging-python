# Testing

This guide covers the testing strategy, structure, and practices for `azure-functions-logging`.

## Running Tests

### All Tests

```bash
make test
```

Or using Hatch:

```bash
hatch run test
```

Both commands run the full test suite via pytest.

### With Coverage

```bash
make cov
```

Or:

```bash
hatch run cov
```

This generates a coverage report showing line-by-line coverage for the entire package.

### Specific Test File

```bash
pytest tests/test_formatter.py
```

### Tests Matching a Pattern

```bash
pytest -k "test_json"
```

### Verbose Output

```bash
pytest -v tests/
```

## Test Structure

All tests reside in the `tests/` directory:

```
tests/
-- test_context.py          # Context injection, binding, and ContextFilter tests
-- test_formatter.py        # ColorFormatter tests
-- test_host_config.py      # host.json conflict detection tests
-- test_integration.py      # End-to-end integration tests
-- test_json_formatter.py   # JsonFormatter tests
-- test_logger.py           # FunctionLogger wrapper tests
-- test_setup.py            # Logging setup and configuration tests
```

### test_setup.py

Tests for the `setup_logging()` function and overall logging system configuration:

- Default setup creates a handler with `ColorFormatter`
- `format="json"` creates a handler with `JsonFormatter`
- Idempotent setup (multiple calls do not add duplicate handlers)
- Custom log level configuration
- Invalid format raises `ValueError`

### test_formatter.py

Tests for `ColorFormatter`:

- Format string structure: `HH:MM:SS LEVEL logger message`
- Color codes per level (DEBUG gray, INFO blue, WARNING yellow, ERROR red, CRITICAL bold red)
- Context fields appended when present
- Exception formatting with readable stack traces
- Cold start indicator in output

### test_json_formatter.py

Tests for `JsonFormatter`:

- Output is valid JSON (single line per record)
- All required fields present: timestamp, level, logger, message
- Context fields included when set: invocation_id, function_name, trace_id, span_id, cold_start, host_instance_id
- Extra fields from `bind()` and keyword arguments included in `extra` object
- Exception traceback included in `exception` field
- Timestamp format is ISO 8601

### test_context.py

Tests for context injection, binding, and the ContextFilter:

**inject_context tests**:

- Extracts invocation_id, function_name, trace_id, span_id from context object
- Trace ID and span ID extracted from W3C traceparent header (second and third fields of `trace_parent`)
- Cold start detection (first call returns True, subsequent calls return False)
- Handles missing attributes gracefully (defaults to None)
- Handles None context without raising
- Thread safety via contextvars

**ContextFilter tests**:

- Filter attaches context fields to LogRecord
- Filter works with no context set (fields default to None)
- Filter does not raise on any input

### test_logger.py

Tests for the `FunctionLogger` wrapper class:

- All standard log methods delegate to the wrapped logger (debug, info, warning, error, critical, exception)
- `bind()` returns a new `FunctionLogger` with merged context
- Binding is immutable (original logger is not modified)
- Cumulative binding (bind on a bound logger combines both contexts)
- `clear_context()` removes all bound fields
- `setLevel()`, `isEnabledFor()`, `getEffectiveLevel()` delegate correctly
- `name` property returns the underlying logger name

### test_host_config.py

Tests for `host.json` conflict detection:

- Warns when host.json logLevel is more restrictive than configured level
- No warning when host.json logLevel matches or is less restrictive
- No warning when host.json is missing
- Handles malformed host.json gracefully

### test_integration.py

End-to-end integration tests:

- Full logging pipeline with ColorFormatter produces expected output
- Full logging pipeline with JsonFormatter produces valid JSON with all fields
- Context injection and log output work together correctly

## Writing Tests

### Test File Naming

Test files follow the `test_*.py` naming convention. Each test file corresponds to a logical area of the library.

### Test Function Naming

Use descriptive names that explain the expected behavior:

```python
def test_setup_logging_with_json_format_creates_json_formatter():
    ...

def test_inject_context_with_missing_attributes_defaults_to_none():
    ...

def test_cold_start_is_true_only_on_first_invocation():
    ...
```

### Test Structure

```python
import logging
import pytest
from azure_functions_logging import setup_logging, get_logger, inject_context

def test_basic_logging_setup():
    """setup_logging() configures the root logger with a handler."""
    # Arrange
    setup_logging()

    # Act
    logger = get_logger(__name__)
    logger.info("test message")

    # Assert
    root = logging.getLogger()
    assert len(root.handlers) >= 1
```

### Testing Context

When testing context injection, create a mock context object:

```python
class MockContext:
    invocation_id = "test-invocation-id"
    function_name = "TestFunction"

    class trace_context:
        trace_parent = "00-abcdef1234567890abcdef1234567890-1234567890abcdef-01"

def test_inject_context_sets_fields():
    inject_context(MockContext())
    logger = get_logger(__name__)
    # Verify context fields appear in output
```

### Testing Formatters

Capture log output using a `StringIO` handler:

```python
import io
import logging

def test_json_formatter_output():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger("test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("test message")

    output = stream.getvalue()
    data = json.loads(output)
    assert data["message"] == "test message"
    assert data["level"] == "INFO"
```

## CI Test Matrix

Tests run automatically on every pull request and push to `main`. The CI matrix covers:

| Python Version | Status |
| -------------- | ------ |
| 3.10 | Tested |
| 3.11 | Tested |
| 3.12 | Tested |
| 3.13 | Tested |
| 3.14 | Tested |

All tests must pass across the entire matrix before a pull request can be merged.

## Coverage

Coverage is tracked via pytest-cov and reported to Codecov. The current coverage badge is visible in the project README.

To check coverage locally:

```bash
make cov
```

The report shows:

- Line coverage per module
- Branch coverage per module
- Uncovered lines highlighted

When adding new features, ensure coverage does not decrease. New code should have corresponding test coverage.

## Test Best Practices

- **Isolate tests**: Each test should be independent and not rely on state from other tests
- **Clean up**: Reset logging handlers and contextvars after tests to avoid interference
- **Use fixtures**: Leverage pytest fixtures for common setup (mock contexts, loggers, handlers)
- **Test edge cases**: Missing attributes, None values, empty strings, concurrent access
- **Test the public API**: Focus on testing through `setup_logging()`, `get_logger()`, and `inject_context()` rather than internal implementations
- **Regression tests**: Every bug fix must include a test that would have caught the bug

## Real Azure E2E Tests

The project includes a real Azure end-to-end test workflow that deploys an actual Function App to Azure and validates HTTP endpoints.

### Workflow

- **File**: `.github/workflows/e2e-azure.yml`
- **Trigger**: Manual (`workflow_dispatch`) or weekly schedule (Mondays 02:00 UTC)
- **Infrastructure**: Azure Consumption plan, `koreacentral` region
- **Cleanup**: Resource group deleted immediately after tests (`if: always()`)

### Running E2E Tests

```bash
gh workflow run e2e-azure.yml --ref main
```

### Required Secrets & Variables

| Name | Type | Description |
| --- | --- | --- |
| `AZURE_CLIENT_ID` | Secret | App Registration Client ID (OIDC) |
| `AZURE_TENANT_ID` | Secret | Azure Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Secret | Azure Subscription ID |
| `AZURE_LOCATION` | Variable | Azure region (default: `koreacentral`) |

### Test Report

HTML test report is uploaded as a GitHub Actions artifact (retained 30 days).
