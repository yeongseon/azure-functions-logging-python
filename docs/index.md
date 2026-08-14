# Azure Functions Logging

Production-oriented, developer-friendly logging for the Azure Functions Python v2 programming model.

`azure-functions-logging` keeps setup small while giving you structured context, cold start visibility, and practical local ergonomics.

## Five-Second Start

Copy this into your function module:

```python
from azure_functions_logging import get_logger, logging_context, setup_logging

setup_logging()
logger = get_logger(__name__)

logger.info("logging initialized")
```

That setup is enough to begin.

## Why Teams Use It

Azure Functions projects often outgrow default logging quickly:

- Raw logs are hard to scan locally.
- Invocation metadata is missing unless manually carried around.
- Startup behavior is unclear during cold-start debugging.
- Local and production log consumers need different output formats.

This library addresses those gaps with a small API surface.

## Core Features

- `setup_logging()` one-liner startup configuration.
- Local colorized output (`format="color"`) for fast visual scanning.
- Structured NDJSON output (`format="json"`) for production ingestion.
- `logging_context(context)` context manager that always restores prior context on exit (recommended).
- `inject_context(context)` returns `ContextTokens` for paired `restore_context(tokens)` use in middleware.
- `setup_logging(use_record_factory=True)` opt-in global LogRecordFactory so context flows to every `LogRecord`.
- `JsonFormatter` for host-managed handlers via `setup_logging(functions_formatter=JsonFormatter())`.
- Automatic `cold_start` flag detection on first invocation per process.
- `FunctionLogger.bind()` for immutable request-scoped context binding.
- `FunctionLogger.log()` and `FunctionLogger.hasHandlers()` for stdlib parity.
- Host-level `host.json` conflict warnings, with `host_json_path=` override and bounded parent-walk discovery.
- `setup_logging(activate_trace_context=True)` binds the host's W3C trace context so OpenTelemetry log records inherit the invocation's `trace_id` / `span_id` — see [OpenTelemetry trace correlation](opentelemetry.md), verified with real Application Insights portal captures.
- Idempotent setup to avoid duplicate reconfiguration.

## What Gets Logged

Depending on formatter and context, events include:

- Timestamp, level, logger name, message.
- Invocation metadata: `invocation_id`, `function_name`, `trace_id` and `span_id` (from W3C `traceparent` headers, strict validation), `cold_start`, and `host_instance_id` (resolved by the formatter/filter).
- Structured per-event fields from keyword arguments.
- Bound context keys from `bind()`.

## Azure Handler Example

```python
import azure.functions as func
from azure_functions_logging import JsonFormatter, get_logger, logging_context, setup_logging

setup_logging(functions_formatter=JsonFormatter())
logger = get_logger(__name__)

app = func.FunctionApp()


@app.route(route="health")
def health(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        request_logger = logger.bind(route="/health", method=req.method)
        request_logger.info("health endpoint called")
        return func.HttpResponse("ok", status_code=200)
```

This combines context-managed invocation context and request binding in a safe, explicit flow that always restores prior context on exit (even on exceptions).

## Environment-Aware Behavior

Behavior changes intentionally by runtime:

- Local standalone process: sets the target/root logger level; adds a `StreamHandler` (`color` or `json`) only if no handlers exist, otherwise just attaches filters to existing handlers.
- Azure/Core Tools runtime: installs `ContextFilter` on existing root handlers **and on the root logger itself** (so direct calls on the root logger carry context); does not add handlers or change root level. To guarantee context on records that propagate from named child loggers to handlers attached later, pass `use_record_factory=True` to `setup_logging()`.

!!! warning
    In Azure-hosted execution, host-level `host.json` settings can still suppress logs even when application-level setup appears correct.

## Recommended Defaults

Use these defaults unless you have a specific reason to diverge:

- Local development: `setup_logging(format="color")`
- Production (standalone): `setup_logging(format="json")`
- Production (Azure Functions / Core Tools): `setup_logging(functions_formatter=JsonFormatter())` — `format="json"` alone is ignored on host-managed handlers
- Logger creation: `get_logger(__name__)`
- Function entrypoint: `with logging_context(context):` wrapping the body, or `tokens = inject_context(context); try: ...; finally: restore_context(tokens)`

## Documentation Map

Start here, then branch by need:

- [Installation](installation.md) for package setup.
- [Quickstart](getting-started.md) for first runnable flow.
- [Configuration](configuration.md) for all `setup_logging()` options.
- [Usage Guide](usage.md) for complete patterns and advanced sections.
- [Examples](examples/basic_setup.md) for scenario-focused snippets.
- [API Reference](api.md) for signatures and typed docs.
- [Troubleshooting](troubleshooting.md) for production incident cases.
- [OpenTelemetry trace correlation](opentelemetry.md) for binding the host invocation's trace context to your logs.
- [FAQ](faq.md) for direct operational questions.

## Design Goals

The library stays intentionally narrow:

- Improve application logging ergonomics.
- Preserve Python standard logging compatibility.
- Keep runtime dependencies minimal.
- Avoid replacing tracing/APM platforms.

It is a focused logging utility, not a full observability stack.

## Next Actions

If you are integrating today:

1. Add the package and call `setup_logging()` once at startup.
2. Wrap each handler body in `with logging_context(context):` (or apply `@with_context`).
3. Add request-scoped keys with `logger.bind()`.
4. Use `setup_logging(functions_formatter=JsonFormatter())` to emit NDJSON on host-managed handlers in Azure.
5. Verify `host.json` level settings (or pass `host_json_path=`) to avoid silent suppression.
When these are complete, your logs become immediately easier to read, correlate, and operate.
