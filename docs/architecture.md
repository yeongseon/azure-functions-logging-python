# Architecture

This document explains how `azure-functions-logging` is structured internally and why key design choices support Azure Functions production behavior.

## Design Objectives

The package is intentionally focused:

- Keep logging setup small for application developers.
- Preserve compatibility with Python standard `logging`.
- Add invocation-aware metadata without invasive patterns.
- Avoid duplicate handlers in runtime-managed environments.
- Stay dependency-light and operationally predictable.

## High-Level Components

Core modules and responsibilities:

- `__init__.py`: public exports and `get_logger()` factory.
- `_setup.py`: setup orchestration, environment detection, idempotency.
- `_logger.py`: `FunctionLogger` wrapper and immutable `bind()` behavior.
- `_context.py`: context variables, `inject_context()`, and `ContextFilter`.
- `_formatter.py`: local color formatter.
- `_json_formatter.py`: structured JSON formatter.
- `_host_config.py`: host policy mismatch warning logic.
- `_decorator.py`: `with_context` decorator for automatic context injection and cleanup.
- `_filters.py`: `SamplingFilter` (rate-limiting) and `RedactionFilter` (PII masking).

## Public API Boundary

Public symbols intentionally kept small:

- `setup_logging`
- `get_logger`
- `FunctionLogger`
- `JsonFormatter`
- `inject_context`
- `logging_context`
- `reset_context`
- `restore_context`
- `ContextTokens`
- `with_context`
- `get_logging_metadata`
- `RedactionFilter`
- `SamplingFilter`
- `AttributeFlattenFilter`
- `__version__`
Everything else remains internal to keep migration and evolution manageable. (`__version__` is exported for programmatic version checks.)

## Setup Pipeline

`setup_logging()` is the entrypoint for configuration.

Behavior summary:

1. Validate input (`format` must be `color` or `json`).
2. Enforce idempotency (per `logger_name` — repeated calls are no-ops).
3. Build `ContextFilter`.
4. Detect runtime environment.
5. Apply local or runtime-safe setup strategy.
6. Check potential host-level log suppression mismatch.

## Environment Detection Strategy

Detection checks the `FUNCTIONS_WORKER_RUNTIME` environment variable to branch between local and runtime-safe paths:

- Present → Azure Functions / Core Tools runtime (host-managed handlers).
- Absent → local standalone Python (needs handler setup).

## Runtime-Safe Behavior in Azure/Core Tools

In Functions runtime contexts, setup avoids replacing host handler graph.

Instead, it:

- Installs `ContextFilter` onto existing root handlers.
- Installs filter on root logger for future handler coverage.
- Optionally sets `functions_formatter` on existing handlers when provided.
- Preserves host-managed output pipeline.

This prevents duplicate output and alignment issues with platform logging.

## Local Standalone Behavior

In non-Functions environments:

- Target logger level is set.
- `StreamHandler` is created only when the target logger has no existing handlers.
- Formatter is selected by `format` parameter when a new handler is created.
- `ContextFilter` is attached for metadata fields.

This gives deterministic local behavior with minimal code.

## Request Flow and Runtime Relationship

`azure-functions-logging` operates at two distinct lifecycle points within the Azure Functions runtime:

1. **Startup** — `setup_logging()` configures handlers, formatters, and filters once during module initialization.
2. **Per-request** — `inject_context()` (or `@with_context`) captures invocation metadata into `contextvars` at the start of each function invocation.

```mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant Host as Azure Functions Host
    participant Worker as Python Worker
    participant Setup as setup_logging()
    participant Handler as Function Handler
    participant Ctx as inject_context()
    participant Logger as FunctionLogger
    participant CF as ContextFilter
    participant Output as Log Output

    rect rgb(240, 248, 255)
    note over Worker,Setup: Startup (once per worker process)
    Worker->>Setup: import → setup_logging()
    Setup->>Setup: detect environment (FUNCTIONS_WORKER_RUNTIME)
    alt Azure / Core Tools runtime
        Setup->>Setup: install ContextFilter on existing host handlers
    else Local standalone
        Setup->>Setup: create StreamHandler + formatter
    end
    end

    rect rgb(255, 248, 240)
    note over Client,Output: Per Invocation
    Client->>Host: HTTP Request
    Host->>Worker: invoke with func.Context
    Worker->>Handler: call function handler
    Handler->>Ctx: inject_context(context)
    Ctx->>Ctx: set contextvars (invocation_id, function_name, ...)
    Handler->>Logger: logger.info("Processing...")
    Logger->>CF: LogRecord passes through ContextFilter
    CF->>CF: copy contextvars onto LogRecord
    CF->>Output: enriched log → stdout / Application Insights
    Handler-->>Worker: return HttpResponse
    Worker-->>Host: response
    end
```

The host manages log shipping to Application Insights. This library enriches log records with invocation context but does not replace or bypass the host's log pipeline.

## Context Propagation Model

Invocation metadata is carried through `contextvars`:

- `invocation_id_var`
- `function_name_var`
- `trace_id_var`
- `span_id_var`
- `cold_start_var`

Benefits of `contextvars`:

- Thread-safe isolation.
- Async task-safe isolation.
- No need to pass context objects through deep call stacks.

## Context Enrichment Flow

Request-level flow:

1. Handler calls `inject_context(context)` (or uses the `@with_context` decorator).
2. Context values are extracted and stored in context variables.
3. `ContextFilter` copies context variable values onto each `LogRecord`.
4. Formatter reads enriched `LogRecord` attributes and outputs the message.

```mermaid
sequenceDiagram
    participant Trigger as HTTP Trigger
    participant Handler as Function Handler
    participant CTX as inject_context()
    participant Vars as contextvars
    participant CF as ContextFilter
    participant LRF as LogRecordFactory
    participant Fmt as Formatter

    Trigger->>Handler: invoke with func.Context
    Handler->>CTX: inject_context(context)
    CTX->>Vars: set invocation_id, function_name, trace_id, cold_start
    Handler->>Handler: logger.info("Processing request")
    alt default mode (ContextFilter)
        Handler->>CF: LogRecord passes through filter
        CF->>Vars: read context variable values
        CF->>CF: copy values onto LogRecord attributes
        CF->>Fmt: enriched LogRecord
    else use_record_factory=True (LogRecordFactory)
        Handler->>LRF: LogRecord created by factory
        LRF->>Vars: read context variable values
        LRF->>LRF: set context attributes at record creation
        LRF->>Fmt: enriched LogRecord
    end
    Fmt-->>Handler: formatted output with context fields
```

This decouples business code from formatter implementation details.

## Cold Start Detection Design

Cold start is process-scoped and simple by design:

- Internal flag starts `True`.
- First `inject_context()` sets `cold_start=True`, then flips flag.
- Future calls in same process return `False`.

This model maps well to Azure Functions worker reuse semantics.

## FunctionLogger Wrapper Pattern

`FunctionLogger` wraps standard loggers rather than replacing logging internals.

Key properties:

- Full standard method familiarity (`info`, `warning`, `exception`, etc.).
- Immutable binding (`bind()` returns a new wrapper).
- Bound keys merged into per-record extra context.

Why wrapper over subclassing global logger:

- Less risky integration with existing libraries.
- Easier incremental adoption.
- Lower chance of side effects in framework code.

## Formatter Responsibilities

### Color Formatter

- Optimized for local human readability.
- Shows timestamp, level, logger, message.
- Includes context metadata when present.
- Appends traceback text for exceptions.

### JSON Formatter

- Outputs one JSON object per line.
- Captures core fields and context metadata.
- Preserves custom record fields under `extra`.
- Supports downstream indexing and analytics workflows.

## host.json Conflict Detection

Host-level settings can suppress app-level log events.

The warning helper:

- Reads `host.json` when present.
- Resolves host default level into logging equivalent.
- Warns if host policy is stricter than configured level.

This closes a common observability blind spot during setup.

## Error Handling Philosophy

The library prioritizes application continuity:

- Context extraction failures are silent and non-fatal.
- Missing context fields degrade to `None`.
- Setup validates format strictly and fails fast for invalid options.
- Host config parsing failures fail safe without crashing the app.

## Operational Implications

For production teams, this architecture means:

- You can adopt gradually without replacing logging foundations.
- Context correlation is easy with a single injection call.
- Local and runtime behavior differ intentionally to match platform constraints.
- Cold start analysis becomes available without custom plumbing.

## Key Design Decisions

### 1. Environment-driven setup strategy

`FUNCTIONS_WORKER_RUNTIME` is the branch variable that determines whether setup runs the Azure/Core Tools path or the local standalone path. `WEBSITE_INSTANCE_ID` is available as a helper signal but is not used in the primary branching logic.

### 2. Idempotent configuration per logger name

`setup_logging()` tracks configured logger names in an internal `_configured_loggers` set. Repeated calls for the same `logger_name` are no-ops. Different logger names each get their own setup pass.

### 3. contextvars for invocation metadata

Invocation-scoped metadata (`invocation_id`, `function_name`, `trace_id`, `cold_start`) is stored in `contextvars` rather than thread-locals or logger attributes. This provides automatic async-task isolation and avoids polluting the global logger namespace.

### 4. Wrapper over logger subclass

`FunctionLogger` wraps a standard `logging.Logger` instance rather than subclassing `logging.Logger` or replacing the logger class globally. This avoids side effects in third-party libraries and allows incremental adoption.

### 5. Process-scoped cold start flag

Cold start detection uses a module-level boolean that starts `True` and flips to `False` after the first `inject_context()` call. This maps directly to the Azure Functions worker process lifecycle without requiring external state.

### 6. Context enrichment: filter or factory

Two complementary mechanisms inject context variable values onto each `LogRecord`:

- **`ContextFilter` (default)** runs during the filter phase, before the formatter, and reads context variables at handler-dispatch time. It works with both `ColorFormatter` and `JsonFormatter` but reflects the *current* contextvar state when the handler runs — not when the record was created.
- **`setup_logging(use_record_factory=True)`** swaps the global `logging.LogRecordFactory` so context fields are captured at record-creation time. This snapshot survives thread hops, queued/delayed handlers, and contextvar resets between record creation and handler dispatch.

When `use_record_factory=True`, `ContextFilter` is intentionally **not** attached to handlers, so the factory snapshot is the single source of truth and cannot be overwritten downstream.

## Module Boundaries

```mermaid
flowchart TD
    INIT["__init__.py\nPublic API exports"]
    SETUP["_setup.py\nsetup_logging()"]
    CTX["_context.py\ninject_context() + ContextFilter"]
    LOG["_logger.py\nFunctionLogger + bind()"]
    DEC["_decorator.py\n@with_context"]
    FILT["_filters.py\nSamplingFilter + RedactionFilter"]
    FMT["_formatter.py\nColorFormatter"]
    JSON["_json_formatter.py\nJsonFormatter"]
    HOST["_host_config.py\nhost.json conflict detection"]

    INIT --> SETUP
    INIT --> CTX
    INIT --> LOG
    INIT --> JSON
    INIT --> DEC
    INIT --> FILT
    SETUP --> CTX
    SETUP --> FMT
    SETUP --> JSON
    SETUP --> HOST
    DEC --> CTX
```

## Related Documents

- [Usage Guide](usage.md)
- [Configuration](configuration.md)
- [API Reference](api.md)
- [Troubleshooting](troubleshooting.md)

## Sources

- [Azure Functions Python developer reference](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [Monitor Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-monitoring)
- [host.json logging configuration](https://learn.microsoft.com/en-us/azure/azure-functions/functions-host-json#logging)
- [Supported languages in Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/supported-languages)

## See Also

- [azure-functions-validation — Architecture](https://github.com/yeongseon/azure-functions-validation) — Request/response validation and serialization
- [azure-functions-openapi — Architecture](https://github.com/yeongseon/azure-functions-openapi) — API documentation and spec generation
- [azure-functions-doctor — Architecture](https://github.com/yeongseon/azure-functions-doctor) — Pre-deploy diagnostic CLI
- [azure-functions-scaffold — Architecture](https://github.com/yeongseon/azure-functions-scaffold) — Project scaffolding CLI
- [azure-functions-langgraph — Architecture](https://github.com/yeongseon/azure-functions-langgraph) — LangGraph runtime exposure for Azure Functions
