# How Correlation Works

How `azure-functions-logging` turns a per-invocation identifier into the `invocation_id` on every log record, and how that relates to Application Insights correlation.

!!! note "Scope of this page"
    Claims here are limited to the public gRPC proto contract and behavior you can observe from user code — no host-internal narration.
    External citations are pinned to a specific tag or commit, not a moving branch.
    Links verified 2026-08-26.

## 1. Where `invocation_id` comes from

Every function execution is driven by the Azure Functions host, which sends the language worker an `InvocationRequest` over gRPC. That message carries a unique per-invocation id:

```proto
message InvocationRequest {
  // Unique id for each invocation
  string invocation_id = 1;
  ...
}
```

— [`FunctionRpc.proto`, `InvocationRequest.invocation_id`](https://github.com/Azure/azure-functions-language-worker-protobuf/blob/v1.14.0-protofile/src/proto/FunctionRpc.proto#L384-L386) (tag `v1.14.0-protofile`). This is the contract: the id is assigned by the host, one per invocation, and delivered to the worker.

## 2. How it reaches your handler

The Python worker surfaces that id to user code through the `func.Context` object it passes to your handler. The public library defines it as an abstract property:

```python
class Context(abc.ABC):
    """Function invocation context."""

    @property
    @abc.abstractmethod
    def invocation_id(self) -> str:
        """Function invocation ID."""
```

— [`Context.invocation_id`](https://github.com/Azure/azure-functions-python-library/blob/2.2.0/azure/functions/_abc.py#L97-L104) (tag `2.2.0`). So `context.invocation_id` inside your handler **is** the id from §1. This library reads it with `getattr(context, "invocation_id")` — nothing more exotic. That is the entire bridge from host to log field.

```python
with logging_context(context):
    logger.info("processing")  # record now carries context.invocation_id
```

## 3. Two ways the id lands on a record

Once the id is bound (via `logging_context`, `inject_context`, or `@with_context`), it is stored in a `contextvars.ContextVar` and copied onto each `LogRecord` by one of two mutually exclusive mechanisms:

| Mode | Mechanism | When to use |
| --- | --- | --- |
| Default | `ContextFilter` attached to existing handlers | Standard setup; handlers known at `setup_logging()` time |
| `use_record_factory=True` | Global `LogRecordFactory` injects at record creation | Handlers added *after* setup, or loggers that bypass the filter chain |

Both read the same bound context and produce the same `invocation_id` on the record — they differ only in *where* in the logging pipeline the injection happens. They are never combined (see [Architecture](architecture.md)).

## 4. Why background threads lose the id

`contextvars` are bound to the running thread. Python does **not** automatically copy the current context into a new `threading.Thread` or a `ThreadPoolExecutor` worker — see the [CPython `contextvars` documentation](https://docs.python.org/3.12/library/contextvars.html). So a record emitted from a thread you spawned inside the handler will have **no** `invocation_id`, even though the parent invocation had one.

The fix is explicit propagation:

```python
from concurrent.futures import ThreadPoolExecutor
from azure_functions_logging import logging_context, propagate_context

with logging_context(context):
    with ThreadPoolExecutor() as pool:
        pool.submit(propagate_context(do_work, context=context), payload)
```

`propagate_context()` binds the current invocation context to the callable so it stays correlated on the worker thread. This is opt-in and correlation-only; the library never monkeypatches `threading` / `concurrent.futures`. See [Troubleshooting: background-thread logs lose `invocation_id`](troubleshooting.md#background-thread-logs-lose-invocation_id).

## 5. Relationship to Application Insights `operation_Id`

`invocation_id` is **this library's** field: a stable key you control, present on every record, ideal for `where invocation_id == "..."` queries. Application Insights has its own distributed-correlation model built on the W3C [Trace Context](https://www.w3.org/TR/2021/REC-trace-context-1-20211123/) recommendation, where telemetry is stitched together by `operation_Id` / `operation_ParentId` — see [Azure Monitor telemetry correlation](https://learn.microsoft.com/en-us/azure/azure-monitor/app/distributed-trace-data).

These are **complementary, not equal**:

- `invocation_id` — always present, owned by this library, guaranteed one-per-invocation from the proto contract (§1).
- `operation_Id` — owned by the host/ingestion pipeline and the W3C trace context; this library does not set or guarantee it.

To also correlate at the trace level, opt into `activate_trace_context=True` so records inherit the invocation's `trace_id` / `span_id` — but that is trace correlation, not the `invocation_id` field described here. If a record has an `invocation_id` but a mismatched or missing `operation_Id`, that is expected: the two identifiers come from different owners.
