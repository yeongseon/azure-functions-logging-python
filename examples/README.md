# Examples

`azure-functions-logging` includes standalone example scripts that demonstrate
every public API feature. Each script runs without Azure Functions installed.

| Role | Path | Description |
| --- | --- | --- |
| Representative | `examples/basic_setup.py` | One-liner `setup_logging()` + `get_logger()` with all log levels. |
| Focused | `examples/json_output.py` | JSON structured output via `setup_logging(format="json")`. |
| Focused | `examples/collision_safe_logging.py` | User fields that collide with `LogRecord` attributes: renamed, dropped or literal-wins, with metadata intact. |
| Focused | `examples/context_injection.py` | `logging_context()` with a mock `func.Context` for invocation metadata. |
| Focused | `examples/context_binding.py` | `logger.bind()` for per-request extra fields. |
| Focused | `examples/request_correlation.py` | Request correlation (`correlation_id`, invocation fields) with allowlisted fields; credentials and raw headers are never logged. |
| Focused | `examples/cold_start_detection.py` | Cold start toggle across consecutive `logging_context()` entries. |
| Deployable app | `examples/otel_app/function_app.py` | OpenTelemetry trace correlation + redaction with `azure-monitor-opentelemetry`; needs optional dependencies and an Application Insights connection string to export (see [below](#opentelemetry-app-examplesotel_app)). |

Run any example directly:

```bash
pip install -e .
python examples/basic_setup.py
```

## OpenTelemetry app (`examples/otel_app`)

`examples/otel_app` is a deployable Function App (not a standalone script) that wires
`azure-monitor-opentelemetry` together with this package: `configure_azure_monitor()`
runs first, then `setup_logging(activate_trace_context=True)`, then a `RedactionFilter`
is attached to the OTel handler. It is the app described in
[docs/opentelemetry.md](../docs/opentelemetry.md).

Optional dependencies (listed in `examples/otel_app/requirements.txt`):
`azure-functions-logging[otel]` and `azure-monitor-opentelemetry`. The base install and
the scripts above need neither.

### Run against a real Application Insights resource

Needs Azure Functions Core Tools, the packages above and an
`APPLICATIONINSIGHTS_CONNECTION_STRING` for an Application Insights resource you own:

```bash
func start --script-root examples/otel_app
```

Only this path can show that telemetry is exported and appears in Application
Insights. It was not run for this README.

### Verify the wiring offline (no Azure subscription)

```bash
pip install -e ".[dev]"
python -m pytest tests/test_examples.py -k TestOtelApp --no-cov
```

The tests run the real `examples/otel_app/function_app.py` handler with
`azure.monitor.opentelemetry` replaced by an in-memory OpenTelemetry pipeline, and also
check that the paths, requirements and commands named here still exist.

| Offline test proves | Offline test does **not** prove |
| --- | --- |
| `configure_azure_monitor()` is called before `setup_logging()`; the host trace id reaches every exported record; the sensitive extra is masked and benign fields survive | that Azure Monitor receives or ingests anything, sampling, network or credential behavior, or what the portal shows |
