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
