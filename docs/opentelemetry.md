# OpenTelemetry trace correlation

`azure-functions-logging` can bind the Azure Functions host's W3C trace context
into your handler so that OpenTelemetry log records inherit the host invocation
span's `trace_id` and `span_id`. This makes your structured logs correlate with
the distributed trace in Application Insights — **without this package creating,
recording, or exporting any spans**.

## What this feature does

- Reads the host-provided `traceparent` / `tracestate` from the invocation
  `context` and **attaches** the extracted W3C context for the duration of the
  handler (via `logging_context` / `with_context`).
- While that context is active, any OpenTelemetry `LoggingHandler` stamps
  emitted records with the host span's `trace_id` / `span_id`.
- Emits `trace_id` and `span_id` in `JsonFormatter` output regardless of
  OpenTelemetry availability (they are `null` when no context is present).

## What this feature does not do

- It does **not** start, record, or export spans — it only *activates* the
  context the host already produced.
- It does **not** replace `azure-monitor-opentelemetry` /
  `configure_azure_monitor()`. You still configure the exporter yourself; this
  package only ensures the host span context is active while your handler runs.
- It is **not** a general distributed-tracing library.

## Installation

The base install stays zero-dependency. Trace-context activation requires the
optional `[otel]` extra:

```bash
pip install "azure-functions-logging[otel]"
```

When OpenTelemetry is not installed, activation degrades to a **silent no-op** —
your logs still emit `trace_id: null` / `span_id: null` and nothing raises.

## Enabling activation

Activation is **opt-in**. The value is resolved in this order (highest priority
first):

1. The per-call `activate_trace_context=` argument on `logging_context()` /
   `@with_context(...)`, when not `None`.
2. The process-wide default set by
   `setup_logging(activate_trace_context=True)`.
3. `False` (the built-in default — no activation).

```python
from azure_functions_logging import setup_logging, logging_context

# Option A: process-wide default
setup_logging(activate_trace_context=True)

def handler(req, context):
    with logging_context(context):  # inherits the default → activates
        ...

# Option B: per-call override (wins over the default either way)
def handler(req, context):
    with logging_context(context, activate_trace_context=True):
        ...
```

You can also use the low-level `activated_trace_context()` context manager
directly if you manage trace headers yourself.

## Required call order

The OpenTelemetry `LoggingHandler` is attached to the root logger by
`configure_azure_monitor()`. `setup_logging()` only decorates handlers that
already exist when it runs. **Call `configure_azure_monitor()` before
`setup_logging()`** so that context filters — and any `RedactionFilter` /
`SamplingFilter` you attach — actually land on the OTel handler:

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from azure_functions_logging import setup_logging

configure_azure_monitor()                    # 1. attaches the OTel handler
setup_logging(activate_trace_context=True)   # 2. decorates the now-present handler
```

If you reverse the order, the OTel handler is added *after* `setup_logging()`
and never receives your filters — PII redaction is silently bypassed. See
[Troubleshooting: PII appears in Application Insights attributes](troubleshooting.md#pii-appears-in-application-insights-attributes-opentelemetry-mode).

For handlers that must be attached *after* `setup_logging()`, pass
`use_record_factory=True` so context is injected at record-creation time instead
of via handler filters.

## Filters in OpenTelemetry mode

In OTel mode the entire `extra` mapping is exported as log **attributes**, which
makes `RedactionFilter` and `SamplingFilter` *more* important, not less — attach
them to the OTel handler. Nested `dict` values in `extra` are silently dropped by
the OTel SDK; use [`AttributeFlattenFilter`](api.md#attributeflattenfilter) to
flatten them into dotted scalar keys (`order={"id": 1}` → `order.id=1`).

```python
import logging

from azure_functions_logging import (
    AttributeFlattenFilter,
    RedactionFilter,
    setup_logging,
)

setup_logging()
for handler in logging.getLogger().handlers:
    handler.addFilter(RedactionFilter())        # mask PII before export
    handler.addFilter(AttributeFlattenFilter())  # keep nested dicts from being dropped
```

## Known limitation: thread boundaries

Trace-context activation uses `contextvars`, which do **not** automatically
propagate across thread boundaries. Logs emitted from
`loop.run_in_executor(...)` or a `ThreadPoolExecutor` worker lose the host span
correlation unless you propagate the context yourself (e.g. by capturing
`contextvars.copy_context()` and running the work inside it). Async code on the
same event loop is unaffected.

## Runnable example

A minimal Function App wiring `azure-monitor-opentelemetry` together with this
package lives in [`examples/otel_app`](https://github.com/yeongseon/azure-functions-logging-python/tree/main/examples/otel_app).
