# Example: Context Injection

`logging_context(context)` enriches log records with invocation metadata from Azure Functions context. It is the recommended scoped API; `inject_context()` / `restore_context()` is the lower-level manual-token form of the same behavior.

## Goal

Wrap the handler body in `with logging_context(context):` and observe `invocation_id`, `function_name`, `trace_id`, `span_id`, and `cold_start` in logs.

## Baseline Handler

```python
import azure.functions as func
from azure_functions_logging import JsonFormatter, get_logger, logging_context, setup_logging

setup_logging(functions_formatter=JsonFormatter())
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="hello")
def hello(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        logger.info("request started")
        return func.HttpResponse("hello")
```

## Fields Added by `logging_context()`

| Field | Source | Example |
| --- | --- | --- |
| `invocation_id` | `context.invocation_id` | `9f87...` |
| `function_name` | `context.function_name` | `hello` |
| `trace_id` | `context.trace_context.trace_parent` (trace ID portion) | `7ed7...` |
| `span_id` | `context.trace_context.trace_parent` (span ID portion) | `b7ad...` |
| `cold_start` | internal first-call detection | `true` or `false` |

## Why Open the Context Block Early

Open `with logging_context(context):` at the very top of each handler, before business logic:

- Every subsequent log call includes invocation metadata.
- Errors logged later in the pipeline still carry correlation fields.
- You avoid partial logs missing context.

## Complete Handler with Error Path

```python
import json
import azure.functions as func
from azure_functions_logging import JsonFormatter, get_logger, logging_context, setup_logging

setup_logging(functions_formatter=JsonFormatter())
logger = get_logger("payments.handler")

app = func.FunctionApp()


@app.route(route="payments")
def payments(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        logger.info("payments request received", method=req.method)

        try:
            body = req.get_json()
            amount = body.get("amount")
            logger.info("validating payload", amount=amount)

            if amount is None:
                logger.warning("missing amount field")
                return func.HttpResponse("invalid payload", status_code=400)

            logger.info("payment accepted", amount=amount)
            return func.HttpResponse(json.dumps({"status": "ok"}), mimetype="application/json")
        except Exception:
            logger.exception("payments handler failed")
            return func.HttpResponse("internal error", status_code=500)
```

## Behavior Outside Azure

`inject_context()` is safe outside Azure.

If your object does not contain expected attributes, fields are set to `None` and execution continues.

```python
from azure_functions_logging import get_logger, inject_context, setup_logging

class DummyContext:
    invocation_id = "local-1"
    function_name = "dummy"


setup_logging(format="json")
logger = get_logger("local")

inject_context(DummyContext())
logger.info("local simulation")
```

## Recommended Request Flow

For each invocation:

1. Open `with logging_context(context):` at the top of the handler.
2. Create optional bound logger for request metadata.
3. Emit lifecycle logs for start, decision points, and completion.
4. Use `logger.exception()` in failure paths.

## Pairing with `bind()`

```python
request_logger = logger.bind(route="/payments", method=req.method)
request_logger.info("processing started")
```

This combines invocation metadata (context injection) with request metadata (binding).

## What to Verify in Output

- `invocation_id` present for every event in invocation.
- `function_name` matches actual function.
- `trace_id` consistent across related events.
- `span_id` consistent with the W3C parent/span portion when trace context is present.
- `cold_start` true only on first invocation per process.

## Common Mistakes

- Opening `with logging_context(context):` after first logs are already emitted.
- Assuming `trace_id` is present when trace context is absent.
- Forgetting the `with logging_context(context):` wrapper in some handlers, causing partial correlation.

!!! tip
    If you use decorators or middleware-like wrappers, open `with logging_context(context):` in the outermost request entrypoint to guarantee consistency.

## Related Examples

- [Basic Setup](basic_setup.md)
- [Context Binding](context_binding.md)
- [Cold Start Detection](cold_start_detection.md)
- [JSON Output](json_output.md)
