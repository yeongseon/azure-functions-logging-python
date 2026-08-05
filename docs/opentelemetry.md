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

> `configure_azure_monitor()` installs the non-deprecated
> `opentelemetry.instrumentation.logging.LoggingHandler`. This package detects
> **any** handler whose class lives under the `opentelemetry.*` namespace, so
> both that handler and the older `opentelemetry.sdk._logs.LoggingHandler` are
> recognised — you do not need to pin a specific handler class.

If you reverse the order, the OTel handler is added *after* `setup_logging()`
and never receives your filters — PII redaction is silently bypassed. See
[Troubleshooting: PII appears in Application Insights attributes](troubleshooting.md#pii-appears-in-application-insights-attributes-opentelemetry-mode).

For handlers that must be attached *after* `setup_logging()`, pass
`use_record_factory=True` so context is injected at record-creation time instead
of via handler filters.

> **`use_record_factory=True` covers context injection only.** It guarantees that
> `trace_id` / `span_id` / invocation fields reach records emitted through
> late-attached handlers, but it does **not** attach `RedactionFilter`,
> `SamplingFilter`, or `AttributeFlattenFilter` to those handlers. Security and
> noise filters must still be added explicitly to any OTel handler created after
> `setup_logging()` (e.g. by a later `configure_azure_monitor()`) — otherwise PII
> redaction and sampling are silently bypassed on that handler.

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

> **Scope `AttributeFlattenFilter` to the OTel handler.** The filter mutates the
> shared `LogRecord` in place, so if the same filter also runs on a standalone
> `JsonFormatter` stream handler your plain JSON output is flattened too: a
> nested `extra={"order": {"id": 1}}` is emitted as `{"order.id": 1}` instead of
> a nested object. That is what you want for OTel attribute export, but usually
> not for local/standalone JSON logs — attach it to the specific OTel handler
> rather than the root logger when both kinds of handler are present.

> **Handler scoping reduces blast radius but does not isolate mutation.** stdlib
> `logging` passes the *same* `LogRecord` object to every handler in sequence, so
> if the OTel handler runs **before** a JSON/stdout handler on the same logger,
> that later handler still sees the flattened record. Scoping the filter to the
> OTel handler shrinks the window but cannot fully isolate in-place mutation when
> multiple handlers process one record. To keep plain JSON output nested, emit it
> on a separate logger (not sharing handlers with the OTel path).

## Known limitation: thread boundaries

Trace-context activation uses `contextvars`, which do **not** automatically
propagate across thread boundaries. Logs emitted from
`loop.run_in_executor(...)` or a `ThreadPoolExecutor` worker lose the host span
correlation unless you propagate the context yourself (e.g. by capturing
`contextvars.copy_context()` and running the work inside it). Async code on the
same event loop is unaffected.

## Behavior change: spans you create become children of the host span

While activation is on, the host invocation span is the **current** span for
the duration of your handler. Any span you start *inside* the handler — e.g.
`tracer.start_as_current_span("work")` — is therefore parented to the host span
instead of becoming a new top-level (root) span. This is usually what you want
(your work nests under the invocation in the Application Insights end-to-end
transaction), but it **is** a trace-structure change for code that previously
created top-level spans. If you need a detached root span, capture a fresh
root context yourself before starting it.

## Runnable example

A minimal Function App wiring `azure-monitor-opentelemetry` together with this
package lives in [`examples/otel_app`](https://github.com/yeongseon/azure-functions-logging-python/tree/main/examples/otel_app).
