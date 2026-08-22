# Product Requirements Document

# azure-functions-logging

## 1. Overview

`azure-functions-logging` is a lightweight logging helper designed to improve the developer
experience of working with logs in Azure Functions Python v2.

Developers building Azure Functions in Python face several logging pain points: visually
dense output, lack of invocation context in log lines, no cold start visibility, and the
difficulty of correlating logs across requests. The Azure Functions worker's logging
pipeline (root logger → `AsyncLoggingHandler` → gRPC → host) adds constraints that
generic logging solutions do not account for.

This project provides a thin layer over Python's standard `logging` module that is
specifically designed to work safely within the Azure Functions worker architecture.

## 2. Goals

### Primary Goals

- Provide colorized, readable log output for local development.
- Automatically inject invocation context (invocation_id, function_name, trace_id) into log records.
- Detect and surface cold starts without user intervention.
- Stay fully compatible with the Azure Functions worker's logging pipeline.
- Require minimal setup — one-liner configuration.
- Maintain full compatibility with Python's standard `logging` module.

### Design Principles

- **Principle 1**: The root logger's handlers and level are never modified in Azure mode. The library may add package-owned filters (e.g. `ContextFilter`) to existing handlers and to the root logger itself; all other configuration targets named child loggers.
- **Principle 2**: In Azure environments, behavior is safe by default — no forced colors, no handler additions, no interference with the worker's `AsyncLoggingHandler`.
- **Principle 3**: Context injection failures never cause application failures. Logging helpers are auxiliary tools.
- **Principle 4**: The API surface stays as close to standard `logging` as possible.

## 3. Non-Goals (v0.1.0)

The initial version (v0.1.0) did not provide the items below. Several have since shipped; this list is kept for historical scope context, with current status annotated. See also §11 "Future Enhancements".

- ~~Full JSON structured logging~~ — **shipped in v0.2.0** (`JsonFormatter`)
- ~~`host.json` log level conflict warning~~ — **shipped in v0.2.0**
- ~~Sampling or log volume control~~ — **shipped** (`SamplingFilter`)
- ~~OpenTelemetry integration~~ — **partially shipped:** opt-in OpenTelemetry *log correlation* via the `[otel]` extra (`activate_trace_context=True`). Span creation / trace export remains a non-goal (see below).
- Async context propagation across threads — **partially shipped:** opt-in, explicit propagation via `propagate_context()` for `ThreadPoolExecutor` / background threads (contextvars still do not follow threads *automatically*; implicit/monkeypatched instrumentation remains a non-goal)
- Distributed tracing — creating, recording, or exporting spans (**permanent non-goal**; use OpenTelemetry or the Application Insights SDK)
- Log aggregation or external backend integrations (still a non-goal)

## 4. Target Users

### Primary Users

- Developers building APIs with Azure Functions (Python v2)
- Developers debugging Azure Functions locally
- Developers who need invocation context in their log lines

### Secondary Users

- Python serverless developers
- Teams adopting the azure-functions-* ecosystem

## 5. Problem Statement

When developing Azure Functions in Python:

- Logs are visually dense and difficult to scan
- Errors do not stand out clearly from info-level noise
- There is no easy way to see which invocation produced which log line
- Cold starts are invisible without manual instrumentation
- `logging.basicConfig()` conflicts with the worker's handler setup
- The worker's `AsyncLoggingHandler` on the root logger means structured `extra` fields
  are lost over gRPC — only the formatted message string survives
- `traceparent` / `trace_id` is available on all trigger types but rarely surfaced in logs

## 6. Key Use Cases

### Use Case 1 — Local Development

A developer runs Azure Functions locally and monitors logs while testing endpoints.

Problem: Logs are difficult to read quickly.
Solution: Colorized log levels allow developers to immediately identify warnings and errors.

### Use Case 2 — Debugging Failures

A function throws an exception during execution.

Problem: The error is buried among other log lines.
Solution: Error logs are highlighted with readable stack traces.

### Use Case 3 — Invocation Correlation

A developer needs to trace which log lines belong to which function invocation.

Problem: Default logs do not include invocation_id or function_name.
Solution: `inject_context()` automatically sets invocation_id, function_name, and trace_id
on all subsequent log records via contextvars.

### Use Case 4 — Cold Start Visibility

A developer wants to know when a cold start occurs.

Problem: Cold starts are invisible without manual instrumentation.
Solution: `inject_context()` detects and flags the first invocation as a cold start.

### Use Case 5 — Context Binding

A developer wants to add custom context (user_id, operation) to log lines.

Problem: Manually passing context to every log call is tedious.
Solution: `logger.bind(user_id="abc")` returns a new logger that includes the context
on every log call.

## 7. Features (v0.1.0)

### 7.1 Colorized Log Output

Log levels are displayed with different colors in local development.

| Level | Color |
| --- | --- |
| DEBUG | Gray |
| INFO | Blue |
| WARNING | Yellow |
| ERROR | Red |
| CRITICAL | Bold Red |

### 7.2 Clean Log Format with Context

Logs are formatted for readability with optional context fields appended.

```text
HH:MM:SS LEVEL    logger_name  message  [invocation_id=xxx, function_name=yyy]
```

Example output:

```text
12:41:23 INFO     http_trigger  Processing request  [invocation_id=abc-123, function_name=my_func, cold_start=true]
12:41:24 WARNING  http_trigger  Missing parameter  [invocation_id=abc-123, function_name=my_func]
12:41:25 ERROR    http_trigger  Validation failed  [invocation_id=abc-123, function_name=my_func]
```

### 7.3 Simple Setup

```python
from azure_functions_logging import setup_logging

setup_logging()
```

Behavior is environment-aware:
- **Standalone local development**: Adds `StreamHandler` with `ColorFormatter`
- **Azure / Core Tools**: Installs `ContextFilter` only (no handlers, no level changes)

### 7.4 Logger Helper

```python
from azure_functions_logging import get_logger

logger = get_logger(__name__)
logger.info("Processing request")
```

Returns a `FunctionLogger` wrapper with `bind()` and `clear_context()` methods.

### 7.5 Invocation Context Injection

```python
from azure_functions_logging import inject_context

def my_function(req, context):
    inject_context(context)
    logger.info("Handling request")  # includes invocation_id, function_name, trace_id
```

Context is propagated via `contextvars` and copied to `LogRecord` attributes by a
`ContextFilter`. This covers all loggers, including third-party libraries.

### 7.6 Context Binding

```python
bound = logger.bind(user_id="abc", operation="checkout")
bound.info("Processing")  # includes user_id + operation + invocation context
```

`bind()` returns a new immutable logger — it does not mutate the original.

### 7.7 Cold Start Detection

Automatically detected on first invocation. Included as `cold_start=true` in log output.

### 7.8 trace_id Extraction

Parsed from `context.trace_context.trace_parent` (W3C Trace Context format).
The extracted `trace_id` matches Application Insights `operation_Id`.

## 8. Public API

Three exports plus a logger class:

| Export | Type | Purpose |
| --- | --- | --- |
| `setup_logging()` | Function | Configure logging for the current environment |
| `get_logger(name)` | Function | Create a `FunctionLogger` instance |
| `inject_context(context)` | Function | Set invocation context from `func.Context` |
| `FunctionLogger` | Class | Logger wrapper with `bind()` and `clear_context()` |

## 9. Architecture

```text
src/azure_functions_logging/
├── __init__.py       # Public API: setup_logging, get_logger, inject_context
├── _context.py       # contextvars, ContextFilter, inject_context, cold_start
├── _formatter.py     # ColorFormatter (local dev), context-aware formatting
├── _logger.py        # FunctionLogger wrapper with bind() convenience
└── _setup.py         # setup_logging(), environment detection
```

Core mechanism:

```
inject_context(func_context)
  → sets contextvars (invocation_id, function_name, trace_id, cold_start)
    → ContextFilter copies contextvars → LogRecord attributes
      → Formatter reads record.invocation_id, etc.
```

## 10. Environment Detection

| Signal | Meaning |
| --- | --- |
| `FUNCTIONS_WORKER_RUNTIME` present | Functions environment (Azure or local Core Tools) |
| `WEBSITE_INSTANCE_ID` present | Azure-hosted (not local Core Tools) |
| Neither present | Standalone local development |

## 11. Future Enhancements

### v0.2.0 — Production Features

- ~~JSON structured formatter (`JsonFormatter`)~~ — **Implemented in v0.2.0**
- ~~`host.json` log level conflict warning~~ — **Implemented in v0.2.0**
- ~~`logger.bind()` for persistent context fields~~ — **Implemented in v0.1.0**

### v0.3.0+ — Advanced

- Log sampling / volume control
- `.catch()` decorator for exception logging
- ~~Async context propagation across threads~~ — **shipped** (explicit `propagate_context()` helper)
- Full OpenTelemetry correlation

## 12. Success Metrics

- Developer adoption and PyPI download statistics
- GitHub stars and community feedback
- Usage in real-world Azure Functions projects
- Reduction in "how to log in Azure Functions" support questions

## 13. Positioning

`azure-functions-logging` is part of the `azure-functions-*` Python ecosystem:

- `azure-functions-validation` — Request/response validation
- `azure-functions-openapi` — OpenAPI generation
- `azure-functions-logging` — Developer-friendly logging
- `azure-functions-doctor` — Project diagnostics

The focus is simplicity, readability, and Azure Functions-specific safety.

## 14. Example-First Design

### Philosophy

Small-ecosystem libraries live or die by the quality of their examples.
If a developer cannot go from `pip install` to readable log output in under five minutes,
the library has already lost. `azure-functions-logging` treats inline code examples
as a first-class deliverable — every feature section above includes a runnable snippet.

### Quick Start (Hello World)

The shortest path from zero to colorized, context-aware logging:

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging()

logger = get_logger(__name__)
logger.info("Processing request")
```

With invocation context in an Azure Function:

```python
import azure.functions as func

from azure_functions_logging import get_logger, inject_context, setup_logging

setup_logging()
logger = get_logger(__name__)


def main(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    inject_context(context)
    logger.info("Handling request")  # includes invocation_id, function_name, trace_id
    return func.HttpResponse("OK")
```

### Why Examples Matter

1. **Lower entry barrier.** A working Hello World in the PRD and README lets developers
   evaluate the library before reading any reference documentation.
2. **AI agent discoverability.** Tools like GitHub Copilot, Cursor, and Claude Code recommend
   libraries based on README, PRD, and example content. Inline code snippets increase the
   chance that AI agents surface `azure-functions-logging` for relevant prompts.
3. **Cookbook role.** For niche ecosystems, inline examples and `docs/` often serve as the
   primary learning material. Every new feature should include a runnable code snippet.
4. **Proven approach.** FastAPI, LangChain, SQLAlchemy, and Pandas all achieved early adoption
   through extensive, copy-paste-friendly examples.

### Examples in This Document

This PRD embeds working code examples throughout the feature sections (7.1 through 7.8).
Each snippet is designed to be copy-pasted into a real Azure Functions project. The inline
approach is intentional — for a logging library, the code IS the documentation.
