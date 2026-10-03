# FAQ

Answers to common production and day-to-day questions about `azure-functions-logging`.

## Does it work outside Azure Functions?

Yes.

The package works in any Python process because it builds on standard `logging`.
Outside Azure Functions, `inject_context()` simply sets fields from whatever object you pass, and Azure-specific fields may remain `None` if not present.

## How do I use it with an existing logging configuration?

Call `setup_logging()` early, and avoid duplicate handler setup.

If your app already configures handlers manually, keep one clear owner for handler creation.
You can still use `get_logger()` and `inject_context()` while preserving your existing formatter strategy.

!!! warning
    Calling both `logging.basicConfig()` and custom root handler setup in the same process often causes duplicate output.

## Should I use JSON or color format?

Use color for local interactive development.
Use JSON for production ingestion and analytics.

Decision rule:

- Human-first terminal workflow: `setup_logging(format="color")`
- Pipeline-first observability workflow: `setup_logging(format="json")`

## How does cold start detection work?

Cold start is derived automatically on `inject_context()`:

- First invocation in a process: `cold_start=True`
- Later invocations in same process: `cold_start=False`

No manual flags are required.

## Can I reuse `bind()` loggers across requests?

You can, but it is not recommended.

`FunctionLogger.bind()` is immutable and returns a new logger with merged context.
For correctness, create bound loggers per invocation or per request scope, then discard them.

Best pattern:

```python
from azure_functions_logging import get_logger

base_logger = get_logger(__name__)

def handle_request(user_id: str) -> None:
    request_logger = base_logger.bind(user_id=user_id)
    request_logger.info("request started")
```

## Why is my log level ignored in Azure?

Azure host configuration can override application intent.

If `host.json` is more restrictive than your setup level, lower-severity logs are suppressed before output.
Review `host.json` `logging.logLevel.default` and function-specific overrides.

## Is it thread-safe and async-safe?

Yes for invocation context propagation.

Context values are stored in `contextvars`, so request context remains isolated between threads and async tasks.

For bound context from `bind()`, immutability helps avoid cross-request mutation issues.

## How do I suppress noisy third-party logs?

Configure specific logger levels with standard logging APIs.

```python
import logging
from azure_functions_logging import setup_logging

setup_logging(level=logging.INFO)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
```

This keeps your app logs visible while reducing dependency noise.

## Why do I see duplicate log lines?

Most duplicates come from multiple handlers on the same logger hierarchy.

Typical causes:

- Setup executed by multiple frameworks.
- Root logger plus child logger both emitting with propagation.
- Existing config plus package setup both attaching handlers.

Inspect your logger graph and keep one primary handler chain.

## Why are `invocation_id` or `trace_id` missing?

Usually `inject_context(context)` was not called early enough, or the context object lacks expected fields.

Call `inject_context(context)` at the top of each function entrypoint before logging business events.

## Can I pass extra structured fields with each log call?

Yes.

`FunctionLogger` supports keyword arguments that flow into log record `extra`, and JSON output includes them under `extra`.

```python
logger.info("payment authorized", order_id="o-123", amount=49.9)
```

## Do I need to instantiate `JsonFormatter` directly?

Usually no.

Prefer `setup_logging(format="json")` and let the package configure formatter wiring.
Instantiate manually only for advanced custom logging setups.

## Can I call `setup_logging()` multiple times?

You can call it safely, but only the first call applies configuration.

Plan configuration ownership so one startup path determines level/format behavior.

## Does it modify non-application loggers?

It enriches records through filter installation behavior tied to configured handlers.
It does not monkey-patch Python logging internals or replace logger classes globally.

## Is this a replacement for distributed tracing tools?

No.

This package improves application logging ergonomics for Azure Functions.
It does not replace OpenTelemetry tracing backends, centralized correlation architecture, or APM systems.

## Recommended baseline for production

Use this baseline:

```python
import logging
from azure_functions_logging import get_logger, logging_context, setup_logging

setup_logging(level=logging.INFO, format="json")
logger = get_logger(__name__)

def handler(context) -> None:
    with logging_context(context):
        logger.info("invocation started")
```

Then tune host-level settings and ingestion rules.

## Related Docs

- [Getting Started](getting-started.md)
- [Configuration](configuration.md)
- [Usage Guide](usage.md)
- [Troubleshooting](troubleshooting.md)
- [API Reference](api.md)
