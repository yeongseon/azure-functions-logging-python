# API Reference

This reference documents the public API exported by `azure_functions_logging`.

Use this page together with:

- [Configuration](configuration.md) for setup behavior by environment.
- [Usage Guide](usage.md) for complete implementation patterns.
- [Examples](examples/basic_setup.md) for runnable snippets.

## setup_logging

::: azure_functions_logging.setup_logging

### Usage Notes

- Call once during startup.
- Default format is `"color"`.
- In Azure/Core Tools runtime, filter-only behavior avoids duplicate handlers.

### Example

```python
import logging
from azure_functions_logging import setup_logging

setup_logging(level=logging.INFO, format="json")
```

### Example: Named Target Logger

```python
from azure_functions_logging import setup_logging

setup_logging(logger_name="my_service")
```

### Example: Invalid Format Handling

```python
from azure_functions_logging import setup_logging

try:
    setup_logging(format="pretty")
except ValueError:
    pass
```

## get_logger

::: azure_functions_logging.get_logger

### Usage Notes

- Returns a `FunctionLogger` wrapper over a standard logger.
- Pass `__name__` for module-level identity.
- Use the wrapper methods like standard logging methods.

### Example

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
logger.info("module logger ready")
```

### Example: Root Logger Wrapper

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging()
root_logger = get_logger()
root_logger.warning("root logger event")
```

## FunctionLogger

::: azure_functions_logging.FunctionLogger

### Usage Notes

- `bind()` returns a new immutable logger wrapper with merged context.
- `clear_context()` clears bound context on that wrapper instance.
- Logging methods mirror standard logger API.

### Example: Binding Context

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging(format="json")
logger = get_logger("checkout")

request_logger = logger.bind(request_id="r-100", user_id="u-55")
request_logger.info("checkout started")
```

### Example: Chained Binding

```python
base = get_logger("service")
l1 = base.bind(tenant_id="tenant-a")
l2 = l1.bind(operation="import")
l2.info("import queued")
```

### Example: Clearing Bound Context

```python
log = get_logger("demo").bind(session="s-1")
log.info("before clear")
log.clear_context()
log.info("after clear")
```

### Example: Exception Logging

```python
log = get_logger("errors")

try:
    raise RuntimeError("boom")
except RuntimeError:
    log.exception("operation failed", phase="load")
```

## JsonFormatter

::: azure_functions_logging.JsonFormatter

### Usage Notes

- Use indirectly via `setup_logging(format="json")` for most cases.
- Produces one JSON object per line (NDJSON style).
- Includes context fields when available on log records.
- Pass `truncate_native_strings=True` to clip string values in `extra` at `max_string_length` characters (default 2048); truncated values are suffixed with `…`. Only strings in `extra` are affected (recursively through dicts/lists) — `message`, ints, floats, and booleans are left intact.

### Example: Automatic Selection

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging(format="json")
logger = get_logger("api")
logger.info("json formatter active", version="v1")
```

### Example: Manual Formatter Wiring

```python
import logging
from azure_functions_logging import JsonFormatter, get_logger

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

target = logging.getLogger("manual")
target.handlers = [handler]
target.setLevel(logging.INFO)

logger = get_logger("manual")
logger.info("manual formatter configured")
```

## SamplingFilter

::: azure_functions_logging.SamplingFilter

### Usage Notes

- `WARNING` and above always pass.
- `name=` scopes sampling to matching logger names; non-matching records bypass sampling.
- `per_logger=False` shares one bucket across all matching records on the filter instance.
- `per_logger=True` gives each `record.name` an independent bucket/window.

### Example: Per-Logger Buckets for Azure SDK Logs

```python
import logging
from azure_functions_logging import SamplingFilter

for handler in logging.getLogger().handlers:
    handler.addFilter(SamplingFilter(rate=10, window=1.0, name="azure", per_logger=True))
```

## RedactionFilter

::: azure_functions_logging.RedactionFilter

## AttributeFlattenFilter

::: azure_functions_logging.AttributeFlattenFilter

### Usage Notes

- Opt-in only. Attach it to a handler/logger to flatten nested `dict` extras
  into dotted scalar keys (e.g. `order={"id": 1}` becomes `order.id=1`).
- Intended for OpenTelemetry pipelines, where nested `dict` attributes are
  silently dropped by the OTel SDK.
- Lists / heterogeneous arrays are left unchanged (emitted as-is under their
  dotted key). Flattening does **not** recurse into lists, so a
  list-of-dicts such as `items=[{"id": 1}]` is passed through verbatim rather
  than expanded into `items.0.id`.
- Non-string dict keys are skipped (they cannot form a queryable dotted path).
- On key collision — e.g. a nested `{"a": {"b": 1}}` and a literal
  `{"a.b": 2}` both mapping to `a.b` — the first value in iteration order wins
  and later collisions are dropped silently.

!!! warning "Attach to specific handlers, not the root logger blindly"
    This filter mutates the `LogRecord` in place, rewriting nested-`dict`
    attributes into new dotted-key attributes. Attach it only to the handlers
    that need flattened output (e.g. your OpenTelemetry handler). Installing it
    on the root logger changes the record schema for **every** downstream
    handler, which can surprise formatters that expect the original nested
    attribute.

```python
from azure_functions_logging import AttributeFlattenFilter

handler.addFilter(AttributeFlattenFilter())
```

## inject_context

::: azure_functions_logging.inject_context

### Usage Notes

- Call at the start of every function invocation.
- Sets invocation metadata in context variables.
- Enables automatic cold start field in output.

### Example: Azure Function Entrypoint

```python
import azure.functions as func
from azure_functions_logging import get_logger, inject_context, setup_logging

setup_logging(format="json")
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="status")
def status(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    inject_context(context)
    logger.info("status request")
    return func.HttpResponse("ok")
```

### Example: Safe with Partial Context Object

```python
from azure_functions_logging import get_logger, inject_context, setup_logging

class PartialContext:
    invocation_id = "local-123"


setup_logging(format="json")
logger = get_logger("partial")

inject_context(PartialContext())
logger.info("partial context accepted")
```

## with_context

::: azure_functions_logging.with_context

## get_logging_metadata

::: azure_functions_logging.get_logging_metadata

### Usage Notes

- Returns the logging metadata dict attached by the `with_context` decorator, or `None` when the function was not decorated.
- Signature: `get_logging_metadata(func: Any) -> dict[str, Any] | None`.

### Example

```python
from azure_functions_logging import get_logging_metadata, with_context


@with_context
def handler(req, context=None):
    ...


metadata = get_logging_metadata(handler)
# -> {"version": 1, "context_param": "context"} or None if not decorated
```

## logging_context

::: azure_functions_logging.logging_context

## propagate_context

::: azure_functions_logging.propagate_context

### Usage Notes

- Binds the current invocation context to a callable so it can run on a
  `ThreadPoolExecutor` worker or a manually created `threading.Thread`, which
  `contextvars` do not reach on their own.
- Wrap **inside** the invocation, immediately before submitting the work; the
  context is snapshotted at wrap time.
- Pass `context=context` to also propagate the Azure worker's
  `thread_local_storage.invocation_id`; propagation failures are silent and never
  crash the caller.

### Example: ThreadPoolExecutor

```python
from concurrent.futures import ThreadPoolExecutor

import azure.functions as func
from azure_functions_logging import logging_context, propagate_context


def handler(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        with ThreadPoolExecutor() as pool:
            future = pool.submit(propagate_context(do_work, context=context), payload)
            future.result()  # log records from do_work carry the invocation context
    return func.HttpResponse("ok")
```

## reset_context

::: azure_functions_logging.reset_context

## restore_context

::: azure_functions_logging.restore_context

## ContextTokens

::: azure_functions_logging.ContextTokens

## End-to-End API Example

```python
import logging
import azure.functions as func
from azure_functions_logging import get_logger, inject_context, setup_logging

setup_logging(level=logging.INFO, format="json")
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="orders")
def orders(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    inject_context(context)
    req_logger = logger.bind(route="/orders", method=req.method)
    req_logger.info("orders request started")
    req_logger.info("orders request completed")
    return func.HttpResponse("ok")
```

## Cross-Reference

- [Getting Started](getting-started.md)
- [Configuration](configuration.md)
- [Usage Guide](usage.md)
- [Troubleshooting](troubleshooting.md)
