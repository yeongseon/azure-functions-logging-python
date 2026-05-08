# Azure Functions Logging

> Part of the **Azure Functions Python DX Toolkit** — dogfood-tested by [azure-functions-cookbook-python](https://github.com/yeongseon/azure-functions-cookbook-python).

[![PyPI](https://img.shields.io/pypi/v/azure-functions-logging.svg)](https://pypi.org/project/azure-functions-logging/)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/azure-functions-logging/)
[![CI](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/ci-test.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/ci-test.yml)
[![Release](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/publish-pypi.yml)
[![Security Scans](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/security.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/yeongseon/azure-functions-logging-python/branch/main/graph/badge.svg)](https://codecov.io/gh/yeongseon/azure-functions-logging-python)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)
[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://yeongseon.github.io/azure-functions-logging-python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Read this in: [한국어](README.ko.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md)

**Invocation-aware observability for Azure Functions Python v2.**
Surfaces `invocation_id`, detects cold starts, warns on `host.json` misconfig, and outputs Application Insights-ready structured logs — without replacing Python's standard `logging`.

---

Part of the **Azure Functions Python DX Toolkit**
→ Bring FastAPI-like developer experience to Azure Functions

## Why this exists

Azure Functions Python logging has specific failure modes that generic logging libraries don't address:

| Problem | What happens | This library |
|---------|-------------|--------------|
| `host.json` log level conflict | Your `INFO` logs silently disappear in Azure | Detects and warns at startup |
| No `invocation_id` in logs | Impossible to correlate logs to a specific execution | Auto-injects from `context` object |
| Cold start invisible | No signal when a new worker instance starts | Detects automatically on first `inject_context()` |
| Noisy third-party loggers | `azure-core`, `urllib3` flood your Application Insights | `SamplingFilter` / `RedactionFilter` |
| Local vs cloud output mismatch | Colorized output breaks in production pipelines | Environment-aware formatter switching |
| PII leaking into logs | Sensitive values accidentally logged as extra fields | `RedactionFilter` with key-based redaction |

## What it does

- **Invocation context** — auto-injects `invocation_id`, `function_name`, `cold_start` into every log
- **Structured JSON output** — Application Insights-ready NDJSON format for production
- **Noise control** — `SamplingFilter` rate-limits chatty third-party loggers
- **PII protection** — `RedactionFilter` masks sensitive fields before they reach log aggregation

> **Scope disclaimer.** This package writes structured JSON to Python `logging` / stdout. How those fields appear in Application Insights depends on the Azure Functions host, worker, logging configuration, and ingestion pipeline. The library does not own ingestion or schema mapping — both `customDimensions`-parsed and raw-`message` shapes are valid in production.

## Before / After

**Without** `azure-functions-logging` — plain `print()` output, no context, no structure:

```python
import azure.functions as func

app = func.FunctionApp()


@app.route(route="orders")
def process_order(req: func.HttpRequest) -> func.HttpResponse:
    print("Processing order")        # no invocation_id, no structure
    print(f"Order: {req.get_json()}")  # PII may leak, no log level
    return func.HttpResponse("OK")
```

Terminal output:

```
Processing order
Order: {'customer': 'Alice', 'total': 99.99}
```

> No invocation ID. No log level. Hard to correlate in Application Insights.

**With** `azure-functions-logging` — structured, queryable, production-ready:

```python
import azure.functions as func

from azure_functions_logging import get_logger, inject_context, setup_logging

setup_logging()
logger = get_logger(__name__)
app = func.FunctionApp()


@app.route(route="orders")
def process_order(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    inject_context(context)
    logger.info("Processing order", order_id="o-999")
    return func.HttpResponse("OK")
```

Local terminal output (colorized):

```
10:30:00 INFO     function_app  Processing order  [invocation_id=abc-123-def, function_name=process_order, cold_start=true]
```

Production output (NDJSON for Application Insights):

```json
{"timestamp": "2024-01-15T10:30:00+00:00", "level": "INFO", "logger": "function_app",
 "message": "Processing order", "invocation_id": "abc-123-def",
 "function_name": "process_order", "trace_id": null, "cold_start": true,
 "exception": null, "extra": {"order_id": "o-999"}}
```

> Every log carries `invocation_id` and `cold_start`. Queryable in Application Insights. Zero `print()` statements.

> **Note:** The exact Application Insights schema depends on your ingestion pipeline. In some deployments JSON fields are parsed into `customDimensions`; in others the JSON stays inside the `message` column. Examples for both shapes are below.

### Query in Application Insights

#### When JSON fields are parsed into `customDimensions`

```kql
traces
| where customDimensions.invocation_id == "abc-123-def"
| project timestamp, message, customDimensions.cold_start, customDimensions.function_name
| order by timestamp asc
```

Find all cold starts in the last hour:

```kql
traces
| where customDimensions.cold_start == "true"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 5m)
```

#### When JSON remains in the `message` column

```kql
traces
| extend payload = parse_json(message)
| where tostring(payload.invocation_id) == "abc-123-def"
| project timestamp, tostring(payload.message), tostring(payload.cold_start), tostring(payload.function_name)
| order by timestamp asc
```

Find all cold starts in the last hour:

```kql
traces
| extend payload = parse_json(message)
| where tostring(payload.cold_start) == "true"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 5m)
```

## What this package does not do

This package does not own:

- **Replacing stdlib logging** — it wraps and enriches Python's standard `logging`, never replaces it
- **Distributed tracing** — use OpenTelemetry or Application Insights SDK for end-to-end trace correlation
- **API documentation** — use [`azure-functions-openapi`](https://github.com/yeongseon/azure-functions-openapi-python) for API documentation and spec generation

## Installation

```bash
pip install azure-functions-logging
```

## Quick Start

```python
import azure.functions as func
from azure_functions_logging import get_logger, logging_context, setup_logging

setup_logging()
logger = get_logger(__name__)

app = func.FunctionApp()

@app.route(route="hello")
def hello(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):  # binds invocation_id, function_name, cold_start; resets on exit
        logger.info("Request received")
        # {"level": "INFO", "invocation_id": "abc-123", "cold_start": true, ...}

        return func.HttpResponse("OK")
```

`logging_context` is the recommended primary pattern: it injects context on enter and **always** resets on exit (even when the handler raises), which prevents stale context from leaking into the next invocation on a reused worker.

For lower-level control or when integrating with custom middleware, `inject_context(context)` and `reset_context()` are exposed individually:

```python
inject_context(context)
try:
    logger.info("Request received")
finally:
    reset_context()
```

Start the Functions host locally (using the [e2e example app](examples/e2e_app)):

```bash
func start
```

### Verify locally and on Azure

After deploying (see [docs/deployment.md](docs/deployment.md)), the same request produces the same response in both environments.

#### Local

```bash
curl -s http://localhost:7071/api/logme?correlation_id=demo-123
```

```json
{"logged": true, "correlation_id": "demo-123"}
```

#### Azure

```bash
curl -s "https://<your-app>.azurewebsites.net/api/logme?correlation_id=demo-123"
```

```json
{"logged": true, "correlation_id": "demo-123"}
```

> Verified against a temporary Azure Functions deployment in koreacentral (Python 3.12, Consumption plan). Response captured and URL anonymized.

## Invocation Context

`inject_context(context)` should be the **first line** of every handler. It binds:

- `invocation_id` — unique per execution, correlates all logs for one request
- `function_name` — the Azure Functions function name
- `trace_id` — trace context from the platform
- `cold_start` — `True` on first invocation of this worker process

> **`cold_start` semantics.** `cold_start=True` means *the first invocation observed by this Python worker process after module load*. It is **not** a platform-level cold start metric and does not correspond to App Service plan / instance allocation cold starts reported by Azure Functions metrics. Subsequent invocations on the same worker emit `cold_start=False` until the worker is recycled.

```python
def my_function(req, context):
    inject_context(context)
    logger.info("handler started")
    # every log from here carries invocation_id and cold_start
```

Without `inject_context()`, these fields are `None` in every log line.

### `with_context` Decorator

For less boilerplate, use the `with_context` decorator instead of calling `inject_context()` manually:

```python
import azure.functions as func
from azure_functions_logging import get_logger, setup_logging, with_context

setup_logging()
logger = get_logger(__name__)

app = func.FunctionApp()

@app.route(route="hello")
@with_context
def hello(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    logger.info("Request received")
    return func.HttpResponse("OK")
```

The decorator finds the `context` parameter by name, calls `inject_context()` before your handler runs, and resets context variables in `finally` after it returns.

Custom parameter name:

```python
@with_context(param="ctx")
def hello(req: func.HttpRequest, ctx: func.Context) -> func.HttpResponse:
    ...
```

Both sync and async handlers are supported.

## Structured JSON Output (Production)

Use JSON format when logs feed Application Insights or any aggregation system:

> **Note:** The `format` parameter only affects handlers created by this library (local development).
> In Azure Functions, the host manages handlers. Use `functions_formatter=JsonFormatter()` to set
> JSON output on host-managed handlers. Passing `format="json"` in Azure emits a warning.

For standalone local development or CI output:

```python
setup_logging(format="json")
```

For Azure Functions / Core Tools, the host owns the handlers. To force JSON
formatting on existing host-managed handlers:

```python
from azure_functions_logging import JsonFormatter, setup_logging

setup_logging(functions_formatter=JsonFormatter())
```

Output per log line (NDJSON — one JSON object per line):

```json
{"timestamp": "2024-01-15T10:30:00+00:00", "level": "INFO", "logger": "my_module",
 "message": "order accepted", "invocation_id": "abc-123", "function_name": "OrderHandler",
 "cold_start": false, "trace_id": "00-abc...", "exception": null,
 "extra": {"order_id": "o-999"}}
```

Extra fields appear in `extra` and are indexable in Application Insights:

```python
logger.info("order accepted", order_id="o-999", tenant_id="t-1")
```

## host.json Conflict Detection

If your `host.json` suppresses log levels that your app emits, you get this warning at startup:

```
WARNING: host.json logLevel.default is 'Warning'. Logs below WARNING will be suppressed in Azure.
```

Recommended `host.json` baseline:

```json
{
  "version": "2.0",
  "logging": {
    "logLevel": {
      "default": "Information",
      "Function": "Information"
    }
  }
}
```

## Noise Control

Suppress chatty third-party loggers without removing them:

```python
from azure_functions_logging import SamplingFilter, setup_logging
import logging

setup_logging()

# Allow up to 10 azure-core messages per 1-second window
logging.getLogger("azure").addFilter(SamplingFilter(rate=10))

# Silence urllib3 completely in production
logging.getLogger("urllib3").setLevel(logging.WARNING)
```

## PII Redaction

Strip sensitive fields before they reach Application Insights:

```python
from azure_functions_logging import RedactionFilter, setup_logging
import logging

setup_logging()
root = logging.getLogger()
root.addFilter(RedactionFilter(sensitive_keys=["password", "token", "secret"]))
```

Any log record with extra fields whose keys match a sensitive key will have those values replaced with `***`.

## Local vs Cloud

| Environment | Format | Behavior |
|-------------|--------|---------|
| Local terminal | `color` (default) | Colorized `[TIME] [LEVEL] [LOGGER] message` |
| Azure / Core Tools | host-managed | Installs context filters only; pass `functions_formatter=JsonFormatter()` to force NDJSON on host handlers |
| CI / pipeline | `json` | NDJSON, machine-parseable |

`setup_logging()` detects `FUNCTIONS_WORKER_RUNTIME` and `WEBSITE_INSTANCE_ID` to choose the right path automatically. In Azure, it installs context filters without adding handlers (avoids duplicate output from the host pipeline).

## Context Binding

Attach request-scoped metadata to every log without passing it through every call:

```python
def process_order(order_id: str) -> None:
    order_logger = logger.bind(order_id=order_id, region="eastus")
    order_logger.info("processing started")   # includes order_id + region
    order_logger.info("processing complete")  # same metadata, new message
```

Create bound loggers per-invocation. Do not cache them at module level.

## When to use

- You need structured, queryable logs in Application Insights
- You want `invocation_id` correlation across all logs for a single request
- You need cold start detection without custom instrumentation
- You want PII redaction or noise control for third-party loggers
- Your `host.json` config silently suppresses logs and you don't know why

## Documentation

- Full docs: [yeongseon.github.io/azure-functions-logging-python](https://yeongseon.github.io/azure-functions-logging-python/)
- [Configuration reference](https://yeongseon.github.io/azure-functions-logging-python/configuration/)
- [Troubleshooting guide](https://yeongseon.github.io/azure-functions-logging-python/troubleshooting/)
- [API reference](https://yeongseon.github.io/azure-functions-logging-python/api/)

## Ecosystem

This package is part of the **Azure Functions Python DX Toolkit**.

**Design principle:** `azure-functions-logging` owns structured logging and invocation-aware observability. It enriches Python's standard `logging` — it does not replace it. Adjacent concerns belong to [`azure-functions-openapi`](https://github.com/yeongseon/azure-functions-openapi-python) (API documentation and spec generation), [`azure-functions-validation`](https://github.com/yeongseon/azure-functions-validation-python) (request/response validation and serialization), and [`azure-functions-langgraph`](https://github.com/yeongseon/azure-functions-langgraph-python) (LangGraph runtime exposure).

| Package | Role |
|---------|------|
| [azure-functions-openapi-python](https://github.com/yeongseon/azure-functions-openapi-python) | OpenAPI spec generation and Swagger UI |
| [azure-functions-validation-python](https://github.com/yeongseon/azure-functions-validation-python) | Request/response validation and serialization |
| [azure-functions-db-python](https://github.com/yeongseon/azure-functions-db-python) | Database bindings for SQL, PostgreSQL, MySQL, SQLite, and Cosmos DB |
| [azure-functions-langgraph-python](https://github.com/yeongseon/azure-functions-langgraph-python) | LangGraph deployment adapter for Azure Functions |
| [azure-functions-scaffold-python](https://github.com/yeongseon/azure-functions-scaffold-python) | Project scaffolding CLI |
| **azure-functions-logging-python** | Structured logging and observability |
| [azure-functions-doctor-python](https://github.com/yeongseon/azure-functions-doctor-python) | Pre-deploy diagnostic CLI |
| [azure-functions-durable-graph-python](https://github.com/yeongseon/azure-functions-durable-graph-python) | Manifest-first graph runtime with Durable Functions *(experimental)* |
| [azure-functions-knowledge-python](https://github.com/yeongseon/azure-functions-knowledge-python) | Knowledge retrieval (RAG) decorators |
| [azure-functions-cookbook-python](https://github.com/yeongseon/azure-functions-cookbook-python) | Dogfood examples — runnable recipes that exercise the full toolkit |


## For AI Coding Assistants

This package provides structured logging for Azure Functions with zero modifications to stdlib logging.

**LLM-Friendly Resources:**
- `llms.txt` — Concise API reference and quick start (repo root)
- `llms-full.txt` — Complete API signatures, patterns, and design principles (repo root)

**Key Implementation Details for Code Generation:**

1. **Never modify root logger** — Only install filters/formatters on handlers
2. **Context injection is contextvar-based** — Not thread-local, works with asyncio
3. **Idempotent setup** — Calling setup_logging() multiple times is safe
4. **Two environments, two behaviors**:
   - Azure/Core Tools: Only install filters on existing root handlers (respects host.json)
   - Local dev: Add ColorFormatter or JsonFormatter handler to specified logger
5. **Test-friendly**:
   - `inject_context()` accepts any object (no hard dependency on azure.functions.Context)
   - `with_context` decorator works with sync and async handlers
   - Use `reset_context()` in test teardown if needed

**When generating code:**
- Import only from `azure_functions_logging` public API (no underscores)
- Call `setup_logging()` at module level or handler startup (not per-request)
- Prefer `with logging_context(context):` in handlers; use raw `inject_context(context)` only with `try/finally reset_context()`
- Use `logger.bind(key=value)` for per-request fields (not direct logger.extra)
- Apply `RedactionFilter` for PII fields, `SamplingFilter` for high-volume logs

**Example Pattern:**
```python
from azure_functions_logging import setup_logging, get_logger, inject_context

# Module level
setup_logging()
logger = get_logger(__name__)

# Per handler
def my_function(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    inject_context(context)
    req_logger = logger.bind(correlation_id=req.params.get("id"))
    req_logger.info("Processing")
    return func.HttpResponse("OK")
```


This project is an independent community project and is not affiliated with,
endorsed by, or maintained by Microsoft.

Azure and Azure Functions are trademarks of Microsoft Corporation.

## License

MIT
