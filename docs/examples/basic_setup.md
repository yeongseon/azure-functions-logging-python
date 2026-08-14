# Example: Basic Setup

This example shows a complete local-first setup using `setup_logging()` and `get_logger()` with standard log levels.

## Goal

You will configure logging once, emit all severity levels, and verify expected output shape.

## Example Code

```python
import logging
from azure_functions_logging import get_logger, setup_logging

# Configure once at startup
setup_logging(level=logging.DEBUG, format="color")

logger = get_logger(__name__)

logger.debug("debug message", component="init")
logger.info("info message", component="init")
logger.warning("warning message", component="init")
logger.error("error message", component="init")

try:
    raise RuntimeError("sample failure")
except RuntimeError:
    logger.exception("exception message", component="init")
```

## What to Expect

Local output should include:

- Timestamp.
- Colorized level text.
- Logger name.
- Message.
- Exception stack trace for `exception()`.

Illustrative output:

```text
14:41:00 DEBUG    __main__  debug message
14:41:00 INFO     __main__  info message
14:41:00 WARNING  __main__  warning message
14:41:00 ERROR    __main__  error message
14:41:00 ERROR    __main__  exception message
Traceback (most recent call last):
  ...
RuntimeError: sample failure
```

## Why This Pattern Works

- `setup_logging()` centralizes configuration.
- `get_logger(__name__)` gives module-specific identity.
- No custom logging framework knowledge required.
- Existing Python logging habits still apply.

## Common Variants

### Variant A: INFO and Above

```python
import logging
from azure_functions_logging import setup_logging

setup_logging(level=logging.INFO)
```

### Variant B: JSON Output

```python
import logging
from azure_functions_logging import setup_logging

setup_logging(level=logging.INFO, format="json")
```

### Variant C: Named Logger Targeting

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging(logger_name="payments")
logger = get_logger("payments.api")
logger.info("named logger active")
```

## Recommended File Layout

```text
my_function_app/
  function_app.py
  requirements.txt
```

Inside `function_app.py`:

- Run setup at import time.
- Keep one logger per module.
- Use bound loggers for request-local metadata.

## Azure Functions Handler Example

```python
import azure.functions as func
from azure_functions_logging import get_logger, logging_context, setup_logging

setup_logging()
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="ping")
def ping(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        logger.info("ping received")
        return func.HttpResponse("pong")
```

This adds invocation context fields automatically when available.

## In Application Insights

After deploying this handler and sending a request to `/api/ping`, query the `traces` table in Application Insights Logs. The exact schema depends on your ingestion pipeline — the `customDimensions`-parsed shape is shown here (see the [deployment query guide](../deployment.md#inspect-traces-and-requests) for the raw-`message` variant).

```kql
traces
| where customDimensions.function_name == "ping"
| project timestamp, message, customDimensions.invocation_id, customDimensions.function_name, customDimensions.cold_start
| order by timestamp asc
```

Expected result (first request on a fresh worker):

| timestamp | message | invocation_id | function_name | cold_start |
| --- | --- | --- | --- | --- |
| 2026-03-14T10:20:30.12Z | ping received | `abc-123-def` | `ping` | `true` |

The same `logger.info("ping received")` call is now correlated by `invocation_id` and carries a `cold_start` signal — no change to your logging calls.

> If your pipeline leaves the JSON inside the `message` column instead, use `extend payload = parse_json(message)` and read `payload.invocation_id` / `payload.cold_start`.

## Troubleshooting Quick Checks

- No logs: confirm `setup_logging()` executed before first log call.
- Missing DEBUG: ensure `level=logging.DEBUG`.
- Duplicate logs: ensure no extra root handlers were added elsewhere.
- Missing context fields: ensure handler body is wrapped in `with logging_context(context):`.

## Production Notes

- Use `format="json"` for ingestion.
- Keep color output for local developer workflows.
- Validate `host.json` level configuration if running in Functions runtime.

## Related Examples

- [JSON Output](json_output.md)
- [Context Injection](context_injection.md)
- [Context Binding](context_binding.md)
- [Cold Start Detection](cold_start_detection.md)
