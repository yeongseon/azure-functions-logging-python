# Quickstart

Get `azure-functions-logging` running in a few minutes, then expand into structured logs, context injection, and request-scoped metadata.

## What You Will Build

In this guide you will:

1. Install the package.
2. Configure logging with `setup_logging()`.
3. Create a logger with `get_logger()`.
4. Run the code locally and inspect output.
5. Learn where to go next for production patterns.

!!! tip
    If you already use the Azure Functions Python v2 model, you only need one additional import and one setup call.

## Prerequisites

Before starting, make sure your environment includes:

- Python 3.10 or newer.
- A virtual environment (recommended).
- An Azure Functions Python project, or any local Python script for first validation.
- Optional: Azure Functions Core Tools if you want to run a local function host.

## Install the Package

Install from PyPI:

```bash
pip install azure-functions-logging
```

If you pin dependencies, add to `requirements.txt`:

```text
azure-functions
azure-functions-logging>=0.10,<1
```

!!! note
    The library has no external runtime dependencies. It builds on Python's standard `logging` module.

## Five-Second Setup

Copy this into your module:

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

logger.info("logging initialized")
```

What this does:

- Calls `setup_logging()` once.
- Uses color output by default in local development.
- Creates a `FunctionLogger` wrapper through `get_logger(__name__)`.

## Minimal Azure Functions Example

Use this pattern for HTTP triggers:

```python
import azure.functions as func
from azure_functions_logging import get_logger, logging_context, setup_logging

setup_logging()
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="health")
def health(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        logger.info("Health check called")
        return func.HttpResponse("ok", status_code=200)
```

Why `logging_context(context)` matters:

- Adds invocation metadata to each log record.
- Enables automatic `cold_start` flagging.
- Keeps your handler code clean and explicit.
- Always restores prior context on exit, even on exceptions.

### Which context API do I use?

Three ways to attach invocation context — pick one:

- `with logging_context(context):` — **recommended.** Scoped, always restores prior context on exit (even on exceptions).
- `@with_context` — decorator form of the same behavior; good when you want the whole handler wrapped implicitly.
- `tokens = inject_context(context)` / `restore_context(tokens)` — manual token form for middleware or framework integrations where you cannot use a `with` block. You are responsible for calling `restore_context(tokens)` in a `finally`.

Bare `inject_context(context)` without a paired `restore_context()` can leak context between invocations in a reused worker — prefer `logging_context`.

## Expected Local Output

With default `format="color"`, you should see lines shaped like:

```text
14:32:10 INFO     my_module  Logging is ready
14:32:12 INFO     function_app  Health check called  [invocation_id=..., function_name=health, trace_id=..., cold_start=true]
```

You will notice:

- Time, level, logger name, and message are always present.
- Context fields appear when available.
- `cold_start=true` appears on the first invocation after process start.

!!! warning
    In Azure-hosted environments, the host controls handlers and level behavior. Your app-level setup does not replace host logging configuration.

## Test Locally in a Script

You can validate behavior without a Function host:

```python
import logging
from azure_functions_logging import get_logger, setup_logging

setup_logging(level=logging.DEBUG)
logger = get_logger("demo")

logger.debug("debug visible")
logger.info("info visible")
logger.warning("warning visible")
logger.error("error visible")
```

This confirms:

- `setup_logging(level=...)` applies locally.
- `get_logger(name)` wraps a standard logger with `FunctionLogger`.
- All standard methods (`debug`, `info`, `warning`, `error`, `critical`, `exception`) are available.

## Test Locally in Azure Functions Core Tools

When running under Core Tools:

1. Start local host.
2. Send a request to your function.
3. Check host output.

Important behavior in Core Tools and Azure environments:

- The library installs `ContextFilter` only.
- It does not add new handlers.
- It respects host-managed logging pipeline.

## Common First Mistakes

Avoid these early pitfalls:

- Calling `setup_logging()` in multiple modules expecting different formats.
- Forgetting to wrap the handler body in `with logging_context(context):`.
- Expecting app-level `level` to override restrictive `host.json` log level.

## Next Steps

Continue with focused guides:

- [Configuration](configuration.md) for parameters and environment behavior.
- [Usage Guide](usage.md) for complete patterns.
- [Basic Setup Example](examples/basic_setup.md) for practical local flow.
- [JSON Output Example](examples/json_output.md) for production structured logs.
- [Context Injection Example](examples/context_injection.md) for Azure context fields.
- [API Reference](api.md) for signatures and types.

## Quick Checklist

Use this checklist before shipping:

- `setup_logging()` called once during startup.
- `get_logger(__name__)` used in modules.
- Handler body wrapped in `with logging_context(context):`.
- Chosen format is aligned with environment (`color` for local, `json` for production pipelines).
- `host.json` logging level reviewed for conflicts.

!!! tip
    Treat logger instances from `bind()` as request-scoped objects. Create them inside invocation logic, not as global mutable state.

When this checklist is green, you are ready for advanced patterns.
