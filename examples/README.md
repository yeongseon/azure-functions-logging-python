# Examples

These are local-only demonstrations using synthetic data, not production security
templates. `e2e_app` is additionally deployed as ephemeral public Azure certification
infrastructure; its anonymous routes must remain compatible with certification.
`otel_app` has anonymous routes for local demonstration. Configure authentication,
restricted ingress and telemetry access before production deployment. Both apps
disable sampling for demonstration/test visibility, not as production guidance.
Query identifiers (`correlation_id`, `order_id`) are logged: never send credentials,
headers, request payloads or PII. Connection strings belong in deployment environment
configuration and must not be printed. See [security boundaries](../SECURITY.md).

`azure-functions-logging` includes standalone example scripts that demonstrate
every public API feature. Each script runs without Azure Functions installed.

| Role | Path | Description |
| --- | --- | --- |
| Representative | `examples/basic_setup.py` | One-liner `setup_logging()` + `get_logger()` with all log levels. |
| Focused | `examples/json_output.py` | JSON structured output via `setup_logging(format="json")`. |
| Focused | `examples/context_injection.py` | `inject_context()` with a mock `func.Context` for invocation metadata. |
| Focused | `examples/context_binding.py` | `logger.bind()` for per-request extra fields. |
| Focused | `examples/cold_start_detection.py` | Cold start toggle across consecutive `inject_context()` calls. |

Run any example directly:

```bash
pip install -e .
python examples/basic_setup.py
```
