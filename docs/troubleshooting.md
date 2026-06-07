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
