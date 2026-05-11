# Usage Guide

This guide covers practical, production-oriented usage of `azure-functions-logging` across local development and Azure Functions runtime deployment.

## Quick Baseline

Start every project with this structure:

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
```

From here, add JSON output, context injection, and binding based on your environment and observability needs.

## 1) Basic Setup

### Local Development Defaults

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

logger.info("application started")
```

Default behavior:

- Level is `INFO`.
- Format is `color`.
- Setup is idempotent.

### Explicit Level Configuration

```python
import logging
from azure_functions_logging import get_logger, setup_logging

setup_logging(level=logging.DEBUG)
logger = get_logger("demo")

logger.debug("debug event")
logger.info("info event")
```

### Explicit Logger Targeting

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging(logger_name="payments")
logger = get_logger("payments.http")
logger.info("named logger configured")
```

!!! tip
    If your application is small to medium-sized, root logger setup with `logger_name=None` is the simplest and safest default.

## 2) JSON Output for Production

Use JSON when logs are consumed by systems, not just humans.

```python
import logging
from azure_functions_logging import get_logger, setup_logging

setup_logging(level=logging.INFO, format="json")
logger = get_logger("orders")

logger.info("service started", service="orders", region="eastus")
```

Typical JSON event shape:

```json
{"timestamp":"...","level":"INFO","logger":"orders","message":"service started","invocation_id":null,"function_name":null,"trace_id":null,"cold_start":null,"exception":null,"extra":{"service":"orders","region":"eastus"}}
```

JSON best practices:

- Keep `message` short and stable.
- Put event dimensions in structured keys.
- Use stable key naming conventions (`tenant_id`, `request_id`, `operation`).

## 3) Context Injection in Azure Functions

Call `inject_context(context)` once per invocation.

```python
import azure.functions as func
from azure_functions_logging import get_logger, inject_context, setup_logging

setup_logging(format="json")
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="hello")
def hello(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    inject_context(context)
    logger.info("request started")
    return func.HttpResponse("ok")
```

Fields populated from context:

- `invocation_id`
- `function_name`
- `trace_id`
- `cold_start`

Why it matters:

- Correlates all logs for one invocation.
- Improves debugging and incident triage.
- Requires no manual propagation across call chains.

## 4) Context Binding with `FunctionLogger.bind()`

Use `bind()` for request-scoped keys that should appear on many events.

```python
from azure_functions_logging import get_logger

logger = get_logger("checkout")
request_logger = logger.bind(request_id="r-1", user_id="u-1")

request_logger.info("validate cart")
request_logger.info("authorize payment")
request_logger.info("create order")
```

Binding behavior:

- Immutable: original logger unchanged.
- Merge-friendly: chaining adds keys.
- Predictable: no hidden global mutable context.

### Chaining Example

```python
base = get_logger("api")
l1 = base.bind(tenant_id="tenant-a")
l2 = l1.bind(operation="import")
l2.info("import started")
```

### Clearing Bound Context

```python
bound = get_logger("demo").bind(session_id="s-123")
bound.info("before clear")
bound.clear_context()
bound.info("after clear")
```

!!! warning
    Do not store request-scoped bound loggers as module-level singletons. Create them per invocation.

## 5) Cold Start Detection

Cold start is automatic and exposed in logs through `cold_start`.

Behavior:

- First invocation after process startup: `cold_start=True`
- Subsequent invocations in same process: `cold_start=False`

No manual state tracking needed.

!!! note "What `cold_start` actually measures"
    `cold_start=True` means *the first invocation observed by this Python worker process after module load*. It is **not** a platform-level cold start metric and does not correspond to App Service plan / instance allocation cold starts reported by Azure Functions metrics. The flag is process-global and flips back to `False` after the first `inject_context()` call on the worker.

### Example with Duration

```python
import time
from azure_functions_logging import get_logger

logger = get_logger("perf")

start = time.perf_counter()
# handler logic
duration_ms = int((time.perf_counter() - start) * 1000)
logger.info("request completed", duration_ms=duration_ms)
```

In JSON mode, this allows easy latency split by cold vs warm path.

## 6) host.json Conflict Awareness

In Azure/Core Tools contexts, host-level log policy can suppress app logs.

If host defaults are stricter than your configured level, the package emits a warning to surface this mismatch.

Potential conflict example:

```json
{
  "logging": {
    "logLevel": {
      "default": "Warning"
    }
  }
}
```

If app setup is `INFO`, lower-severity events can be hidden by host policy.

Recommended baseline:

```json
{
  "logging": {
    "logLevel": {
      "default": "Information"
    }
  }
}
```

## 7) Environment Behavior

`setup_logging()` chooses behavior by runtime detection.

### Local standalone execution

- Sets logger level.
- Adds stream handler if missing.
- Installs context filter (skipped when `use_record_factory=True`; the global LogRecordFactory injects context instead).
- Applies selected formatter.

### Azure Functions / Core Tools

- Does not add handlers.
- Installs context filter for metadata enrichment (skipped when `use_record_factory=True`; the global LogRecordFactory injects context instead).
- Leaves host handler pipeline intact.

This design prevents duplicate logs in runtime-managed environments.

## 8) Complete End-to-End Pattern

```python
import json
import logging
import azure.functions as func
from azure_functions_logging import get_logger, inject_context, setup_logging

setup_logging(level=logging.INFO, format="json")
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="process")
def process(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    inject_context(context)

    request_logger = logger.bind(method=req.method, route="/process")
    request_logger.info("request received")

    try:
        payload = req.get_json()
        user_id = payload.get("user_id")

        user_logger = request_logger.bind(user_id=user_id)
        user_logger.info("payload accepted")

        result = {"status": "ok"}
        user_logger.info("request completed", status="success")
        return func.HttpResponse(json.dumps(result), mimetype="application/json")
    except Exception:
        request_logger.exception("request failed")
        return func.HttpResponse("internal error", status_code=500)
```

## 9) Advanced Patterns

### A) Suppress Noisy Dependency Logs

```python
import logging
from azure_functions_logging import setup_logging

setup_logging(level=logging.INFO, format="json")

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
```

### B) Feature Flags in Logs

```python
feature_logger = get_logger("features").bind(feature="recommendations", version="v2")
feature_logger.info("feature evaluated", outcome="enabled")
```

### C) Operation Timing

```python
import time

op_logger = get_logger("timing").bind(operation="sync")
start = time.perf_counter()
# ... work ...
elapsed_ms = int((time.perf_counter() - start) * 1000)
op_logger.info("operation finished", elapsed_ms=elapsed_ms)
```

## 10) Operational Checklist

Before production rollout:

- `setup_logging()` called once in startup path.
- `format="json"` enabled where logs are machine-consumed.
- `inject_context(context)` present in every handler.
- Request-level metadata attached through `bind()`.
- `host.json` defaults reviewed against required visibility.
- Dependency logger noise controlled with explicit levels.

## 11) Common Pitfalls

- Multiple setup owners in the same process.
- Missing context injection before first log event.
- Expecting app-level level to override restrictive host policy.
- Reusing one bound logger across unrelated invocations.
- Emitting unstructured free-text fields that are hard to query.

## 12) Where to Go Next

- [Getting Started](getting-started.md)
- [Configuration](configuration.md)
- [Basic Setup Example](examples/basic_setup.md)
- [JSON Output Example](examples/json_output.md)
- [Context Injection Example](examples/context_injection.md)
- [Context Binding Example](examples/context_binding.md)
- [Cold Start Detection Example](examples/cold_start_detection.md)
- [API Reference](api.md)
- [Troubleshooting](troubleshooting.md)
