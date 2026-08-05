# Troubleshooting

This guide covers the most common production and local issues when integrating `azure-functions-logging`.

## Logs Not Showing in Azure

### Symptoms

- Handler code runs, but expected logs are missing.
- Only warnings/errors appear, while info/debug do not.

### Root Cause

`host.json` log level policy is more restrictive than application intent.

### Checks

Inspect host configuration:

```json
{
  "logging": {
    "logLevel": {
      "default": "Warning"
    }
  }
}
```

If app setup is `INFO`, `Warning` host policy suppresses info events.

### Resolution

Adjust host defaults or function-specific overrides:

```json
{
  "logging": {
    "logLevel": {
      "default": "Information",
      "Function.MyFunction": "Information"
    }
  }
}
```

!!! warning
    In Azure-hosted execution, host policy is authoritative for emitted levels.

## Duplicate Log Lines

### Symptoms

- Every log appears twice or more.

### Root Cause

Multiple handlers are attached along logger hierarchy.

Typical causes:

- Existing logging setup plus package setup both attach handlers.
- Multiple frameworks configure root independently.
- `logging.basicConfig()` used alongside custom setup.

### Resolution

- Pick one owner for handler configuration.
- Call `setup_logging()` once in startup path.
- Remove duplicate root handlers in your app configuration.

## host.json Conflict Warning Appears

### Meaning

The library detected host policy that can suppress lower log levels than your configured level.

### Action

- Review `host.json` log level defaults.
- Review `AzureFunctionsJobHost__logging__logLevel__...` app settings that
  override `host.json` in Azure.
- Align defaults with operational visibility needs.
- Keep stricter per-category levels only where justified.

This warning is informational but usually points to real missing telemetry.

## Cold Start Not Detected

### Symptoms

- `cold_start` always `False`.
- `cold_start` always `None`.

### Root Causes

- `inject_context(context)` not called.
- Context injection occurs after first log event.
- Warm worker process already handled previous invocation.

### Resolution

Call `inject_context(context)` first in every handler:

```python
def main(req, context):
    inject_context(context)
    logger.info("invocation started")
```

To observe cold start locally:

1. Restart local host.
2. Send first request.
3. Check first event for `cold_start=true`.

## JSON Format Issues

### Symptoms

- Downstream parser fails to parse events.
- Missing custom fields in JSON output.

### Root Causes

- Log sink expects multiline JSON instead of NDJSON.
- Custom fields passed incorrectly.
- Non-JSON preprocessing modifies log lines.

### Resolution

- Ensure one JSON object per line is accepted.
- Pass extra fields via keyword args in logger calls.
- Avoid shell transformations that corrupt line boundaries.

Correct pattern:

```python
logger.info("order accepted", order_id="o-123", tenant_id="t-1")
```

## Color Output Looks Wrong

### Symptoms

- ANSI escape sequences appear literally.
- Colors not rendered in terminal.

### Root Cause

Terminal or sink does not render ANSI color codes.

### Resolution

Use JSON mode in non-interactive or pipeline environments:

```python
setup_logging(format="json")
```

Keep color mode for local interactive terminal sessions.

## setup_logging Has No Effect

### Symptoms

- Later `setup_logging(...)` calls do not change behavior.

### Root Cause

Idempotency: first setup call wins.

### Resolution

- Ensure desired setup call executes first.
- Consolidate startup configuration in one module.

## Invocation Fields Are Missing

### Symptoms

- `invocation_id`, `function_name`, or `trace_id` is `None`.

### Root Causes

- `inject_context(context)` omitted.
- Context object lacks expected attributes.
- Logging occurs before context injection.

### Resolution

- Inject context at entrypoint before any logs.
- Verify function signature includes `context`.

## Third-Party Logs Too Noisy

### Symptoms

- Dependency logs dominate output and hide app events.

### Resolution

Reduce dependency logger levels:

```python
import logging

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
```

Use `INFO` for application events and `WARNING` for noisy dependencies.

## Bound Context Leaks Across Requests

### Symptoms

- Request identifiers from one invocation appear in another.

### Root Cause

A bound logger with request keys was reused globally.

### Resolution

- Create bound loggers per invocation.
- Do not cache request-scoped bound loggers at module level.

Safe pattern:

```python
request_logger = logger.bind(request_id=current_request_id)
request_logger.info("request started")
```

## Azure vs Local Behavior Confusion

### Clarification

Local standalone setup may add handlers and formatter directly.
Azure/Core Tools setup installs filter-only behavior to avoid duplicate host output.

This difference is intentional and expected.

## PII Appears in Application Insights Attributes (OpenTelemetry mode)

### Symptoms

You attached `RedactionFilter` (or `SamplingFilter`), yet sensitive values still
appear as log **attributes** in Application Insights when using
`azure-monitor-opentelemetry` / `configure_azure_monitor()`.

### Root Cause

In OpenTelemetry mode the OTel `LoggingHandler` is added to the root logger by
`configure_azure_monitor()`. `setup_logging()` only decorates handlers that
already exist when it runs, so if you call `setup_logging()` **before**
`configure_azure_monitor()`, the OTel handler never receives your filters and
the entire `extra` mapping is exported unfiltered.

### Resolution

1. Call `configure_azure_monitor()` **before** `setup_logging()` so the OTel
   handler is present when filters are attached.
2. Attach `RedactionFilter` to the OTel handler explicitly:

   ```python
   import logging

   from azure.monitor.opentelemetry import configure_azure_monitor
   from azure_functions_logging import RedactionFilter, setup_logging

   configure_azure_monitor()          # attaches the OTel LoggingHandler to root
   setup_logging()                    # decorates the now-present handler

   redaction = RedactionFilter()
   for handler in logging.getLogger().handlers:
       handler.addFilter(redaction)   # ensure PII masking on the OTel handler
   ```

3. For handlers attached *after* `setup_logging()`, pass
   `use_record_factory=True` so context is injected at record-creation time,
   and re-attach filters to the late handler.

See [OpenTelemetry correlation](opentelemetry.md) for the full ordering guide.

## OpenTelemetry Appears "Not Installed" After a Broken Upgrade

### Symptoms

Trace-context activation silently no-ops (`trace_id` / `span_id` stay `null`) even
though you installed the `[otel]` extra.

### Root Cause

`azure_functions_logging` gates OTel behavior on an internal `is_available()`
probe that imports `opentelemetry.context` / `opentelemetry.propagate`. That probe
catches **any** import exception and caches the result as "unavailable" for the
rest of the process lifetime. A *partial or broken* OpenTelemetry install (e.g. a
half-finished upgrade, or a version mismatch between `opentelemetry-api` and
`opentelemetry-sdk`) therefore looks identical to "OTel is not installed" — the
activation path is skipped and nothing is raised, by design (context injection
must never crash your app).

### Resolution

1. Verify the import works in isolation:

   ```bash
   python -c "import opentelemetry.context, opentelemetry.propagate; print('ok')"
   ```

   If this raises anything other than `ModuleNotFoundError`, your OTel install is
   broken — reinstall a consistent set of `opentelemetry-*` packages.
2. Restart the worker process after fixing the install: the `is_available()`
   result is cached per process and will not re-probe until restart.

### Note on the OTel test path

The `[otel]` extra pins only `opentelemetry-api>=1.24` (no upper bound). Runtime
code imports **only** the stable public `opentelemetry.context` /
`opentelemetry.propagate` APIs. The test suite (`tests/test_otel_spike.py`)
additionally imports the **private** `opentelemetry.sdk._logs` path, which remains
underscore-private upstream and can break on OTel upgrades. This affects tests
only — it is never imported by shipped runtime code.

## Fast Diagnostic Checklist

Run through this list during incidents:

1. Confirm `setup_logging()` called exactly once.
2. Confirm `inject_context(context)` called first in handler.
3. Confirm output format matches sink expectations.
4. Confirm `host.json` level policy allows required severity.
5. Confirm no duplicate root handlers.
6. Confirm bound loggers are request-scoped.

## Need More Help

Use these references for deeper checks:

- [Usage Guide](usage.md)
- [Configuration](configuration.md)
- [FAQ](faq.md)
- [API Reference](api.md)

If behavior still looks wrong, create a minimal reproducible snippet showing setup code, one handler, and one observed log line.
