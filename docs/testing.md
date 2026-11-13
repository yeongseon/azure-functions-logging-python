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

## Test Levels: what each one proves

Only the last two rows involve a real Functions host or Azure telemetry. Everything in
`tests/` that runs under `make test` is an **in-process** check of Python logging
objects (records, handlers, formatters); it does not prove host behavior or
Application Insights ingestion.

| Level | Where it runs | Command | Needs | Proves |
| --- | --- | --- | --- | --- |
| Unit / in-process | every PR, Python 3.11-3.14 (`.github/workflows/ci-test.yml`) | `make test` (or `pytest tests/`) | nothing | Library logic: records, formatters, filters, redaction, setup, decorator. Coverage gate 95% (`fail_under` in `pyproject.toml`). |
| Wheel / minimum-dependency smoke | every PR (`ci-test.yml`) | CI-only jobs | built wheel | The built wheel installs and imports outside the checkout, and the full suite also passes against minimum runtime dependencies. |
| Local host smoke | every PR (`ci-test.yml`, "Real Functions host smoke") | CI-only job using `tests/host_smoke/` | Core Tools v4 + Azurite | A real `func` host boots the decorated handlers and serves HTTP. It does **not** check telemetry ingestion. |
| Scheduled host matrix / OTel canary | weekly or nightly (`.github/workflows/e2e-host-matrix.yml`, `.github/workflows/otel-nightly.yml`) | scheduled workflows | Core Tools + Azurite; latest OpenTelemetry packages | Host-boot drift across Core Tools versions; drift against the newest OpenTelemetry SDK. |
| Local e2e (HTTP) | on demand | `make e2e-local` | a running host at `E2E_BASE_URL` (default `http://localhost:7071`) | `/api/*` endpoints respond; the App Insights test skips without `APPINSIGHTS_NAME`. Cannot create a certification record. |
| Real Azure e2e | release gate (`.github/workflows/e2e-azure.yml`, called by `publish-pypi.yml`) | `make e2e-azure` | `E2E_BASE_URL`, `E2E_EXPECTED_VERSION`, `APPINSIGHTS_NAME`, `E2E_RESOURCE_GROUP`, Azure login with CLI query access | The deployed host runs the candidate wheel and structured fields reach Application Insights (`tests/e2e/test_logging_e2e.py`). Opt-in; credentials and cloud resources required. |

The benchmark (`benchmarks/bench.py`, `make bench`) is opt-in and is not part of the
required unit suite. It measures in-process CPU cost per operation; it is **not**
end-to-end telemetry latency and says nothing about gRPC, host ingestion or
Application Insights.

## Test Map (by behavior)

Names below are real files under `tests/`; `tests/test_testing_docs_map.py` fails
if a documented path disappears.

| Behavior | Test modules |
| --- | --- |
| Context injection, `with_context` / `logging_context`, record-factory strategy and strategy lifetime | `tests/test_context.py`, `tests/test_decorator.py`, `tests/test_strategy_lifetime.py`, `tests/test_postponed_annotations.py`, `tests/test_host_instance.py` |
| Setup, idempotency and configuration limits | `tests/test_setup.py`, `tests/test_setup_api_ceiling.py`, `tests/test_integration.py` |
| Formatting and `FunctionLogger` | `tests/test_formatter.py`, `tests/test_json_formatter.py`, `tests/test_logger.py`, `tests/test_structured_field_extraction.py` |
| Redaction and secure profile | `tests/test_filters.py`, `tests/test_redaction.py`, `tests/test_redaction_authorization.py`, `tests/test_redacted_exceptions.py`, `tests/test_nested_redaction_policy.py`, `tests/test_secure_setup.py`, `tests/test_secure_redaction.py`, `tests/test_secure_sinks.py`, `tests/test_secure_limits.py`, `tests/test_secure_review_regressions.py`, `tests/test_isolated_handler.py` |
| `host.json` diagnostics and OpenTelemetry | `tests/test_host_config.py`, `tests/test_host_config_otel.py`, `tests/test_host_json_remediation.py`, `tests/test_otel.py`, `tests/test_otel_contract.py`, `tests/test_otel_filters.py` |
| Public API, packaging and compatibility contracts | `tests/test_public_api.py`, `tests/test_contracts.py`, `tests/test_metadata_contract.py`, `tests/test_toolkit_metadata.py`, `tests/test_python_version_metadata.py`, `tests/test_sdk_compatibility_policy.py`, `tests/test_examples.py` |
| Correlation assertions | `tests/test_assert_correlation.py` |
| CI, release and security contracts (offline checks of workflows and tools) | `tests/test_ci_workflow_gates.py`, `tests/test_ci_classify_changes.py`, `tests/test_ci_skip_policy.py`, `tests/test_workflow_pin_hygiene.py`, `tests/test_hatch_matrix_lint.py`, `tests/test_makefile_contract.py`, `tests/test_check_pr_format.py`, `tests/test_classify_review_evidence.py`, `tests/test_doc_link_tag_integrity.py`, `tests/test_release_audit.py`, `tests/test_release_audit_history.py`, `tests/test_release_notes.py`, `tests/test_release_verification_workflows.py`, `tests/test_release_workflow_pins.py`, `tests/test_publish_workflow_selection.py`, `tests/test_runtime_advisory_exceptions.py`, `tests/test_runtime_audit_workflow.py`, `tests/test_security_gates.py`, `tests/test_security_reports.py`, `tests/test_deployment_output_security.py`, `tests/test_e2e_marker_entrypoint_contract.py` |
| Local host smoke app | `tests/host_smoke/function_app.py` (executed by CI, not by pytest) |
| Real Azure / Application Insights e2e (opt-in, `-m e2e`) | `tests/e2e/test_logging_e2e.py` |

Pytest options come from `pyproject.toml`: `-m 'not e2e'` keeps e2e tests out of
`make test`, and `--cov` is on by default. The `e2e` marker selects the lanes above.
`FAIL_ON_SKIP=1` makes an unexpectedly skipped test fail the lane (used by
`make e2e-azure`, the OpenTelemetry canary and release checks).

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
    with logging_context(MockContext()):
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
- **Trigger**: a release gate, not a schedule. `publish-pypi.yml` calls it as a reusable workflow
  (`workflow_call`) at the exact ref being published, so every published commit is certified by
  construction. `workflow_dispatch` is kept for standalone verification and debugging.
- **Infrastructure**: provisioned from `infra/main.bicep` — classic Linux Consumption (`Y1`/Dynamic),
  Python 3.12, in the region from the `AZURE_LOCATION` variable (default `koreacentral`)
- **Cleanup**: Resource group deleted immediately after tests (`if: always()`)

!!! note "Hosting plan"
    This workflow still provisions the classic Linux Consumption plan. That plan retires on
    30 September 2028 and will not receive Python versions beyond 3.12, so
    [Flex Consumption](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan) is
    the plan recommended for new deployments — and the one the
    [deployment guide](deployment.md) uses. Migrating the e2e infrastructure is tracked separately.

### Running E2E Tests

Standalone run (certification normally happens inside `publish-pypi.yml`):

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
