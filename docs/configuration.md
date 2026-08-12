# Configuration

This guide documents every `setup_logging()` option and how configuration behaves across local development, Azure Functions Core Tools, and Azure-hosted runtimes.

## Function Signature

```python
def setup_logging(
    *,
    level: int = logging.INFO,
    format: str = "color",
    logger_name: str | None = None,
    functions_formatter: logging.Formatter | None = None,
    host_json_path: Path | str | None = None,
    use_record_factory: bool = False,
    extra_context_vars: dict[str, contextvars.ContextVar[Any]] | None = None,
    activate_trace_context: bool | None = None,
) -> None
```

`setup_logging()` is designed to be called once during startup.

## Configuration Principles

- Idempotent initialization: repeated calls are no-ops.
- Environment-aware behavior: local and Azure runtime paths differ.
- Standard logging compatibility: no custom logging framework required.

!!! note
    In Azure or Core Tools environments, the library intentionally avoids adding handlers to prevent duplicate output.

## Parameter: `level`

`level` controls message filtering in local standalone execution.

Accepted values are standard logging levels:

- `logging.DEBUG`
- `logging.INFO` (default)
- `logging.WARNING`
- `logging.ERROR`
- `logging.CRITICAL`

Example:

```python
import logging
from azure_functions_logging import setup_logging

setup_logging(level=logging.DEBUG)
```

Behavior details:

- Local standalone: applied to target logger.
- Azure/Core Tools: host pipeline governs output; app-level level may be effectively constrained by host config.

## Parameter: `format`

`format` selects output formatter in local standalone mode.

Supported values:

- `"color"` (default)
- `"json"`

Example:

```python
from azure_functions_logging import setup_logging

setup_logging(format="json")
```

If an unsupported value is provided, `setup_logging()` raises `ValueError`.

!!! warning
    Use `format="json"` for machine parsing and centralized ingestion. Color output is optimized for human readability in terminals.

## Parameter: `logger_name`

`logger_name` lets you target a specific logger in local standalone mode.

```python
from azure_functions_logging import setup_logging

setup_logging(logger_name="my_service")
```

When `logger_name` is `None`:

- Local standalone: root logger is configured.
- Azure/Core Tools: root handlers receive `ContextFilter`.

When `logger_name` is set:

- Local standalone: named logger is configured.
- Azure/Core Tools: filter installation still follows runtime-safe behavior.

Practical recommendation:

- Prefer root configuration unless you have a clear logger isolation strategy.

## Parameter: `use_record_factory`

`use_record_factory` is an opt-in flag that also installs a global
`logging.LogRecordFactory` so context fields (`invocation_id`, `function_name`,
`trace_id`, `cold_start`, `host_instance_id`) are injected at LogRecord creation time. It guarantees
context propagation even when handler filters are misconfigured or bypassed by
third-party logging setups.

```python
from azure_functions_logging import setup_logging

setup_logging(format="json", use_record_factory=True)
```

Behavior details:

- Default is `False` to preserve the existing handler-filter-only behavior.
- When `True`, the global `LogRecordFactory` injection strategy is installed once; repeated calls are no-ops.
- When `True`, `ContextFilter` is **not** attached to handlers. The global
  `LogRecordFactory` is the sole source of context fields, so values captured at
  record-creation time survive thread hops, queued handlers, and delayed flushes
  (no filter runs at handler dispatch time to overwrite the snapshot).
- Modifies the **global** `LogRecordFactory` and affects all loggers in the process.
- The context field names (`invocation_id`, `function_name`, `trace_id`,
  `span_id`, `cold_start`, `host_instance_id`) become reserved on every LogRecord; prefer `FunctionLogger`
  (which sanitizes `extra` keys) when this option is enabled.
- Input validation (e.g. `format`) runs **before** the factory is installed, so
  invalid arguments raise `ValueError` without any global side effects.

## Parameter: `extra_context_vars`

`extra_context_vars` is an optional mapping of `field_name -> contextvars.ContextVar`
whose current values `ContextFilter` copies onto each `LogRecord`, alongside the
built-in context fields. Field names must not collide with the built-in fields.
This only applies to the `ContextFilter` strategy and is ignored when
`use_record_factory=True`.

## Parameter: `activate_trace_context`

`activate_trace_context` sets the process-wide default that `logging_context` and
`with_context` consult to attach the host's W3C trace context (via OpenTelemetry),
making OTel log records inherit the host span's `trace_id`/`span_id`. It requires
the `[otel]` extra and degrades to a silent no-op when OpenTelemetry is not
installed. `True`/`False` force the default on/off; the default `None` leaves the
stored default unchanged (which itself defaults to `False` — activation is
strictly opt-in). A per-call `activate_trace_context` argument overrides this default.

## Idempotency and Reconfiguration

`setup_logging()` uses internal setup state to guarantee idempotency.

Implications:

- First call wins.
- Later calls do not replace handler/formatter choices.
- Conflicting setup calls in different modules can lead to surprising expectations.

Best practice:

```python
from azure_functions_logging import setup_logging

# Run once at module import or startup hook
setup_logging(format="json")
```

## Environment Detection

The setup path depends on environment signals:

- Functions environment check: `FUNCTIONS_WORKER_RUNTIME`
- Azure-hosted check: `WEBSITE_INSTANCE_ID`

Execution behavior by environment:

### Local standalone Python process

- Sets logger level.
- Adds `StreamHandler` if no handlers exist.
- Installs `ContextFilter` on handlers (skipped when `use_record_factory=True`).
- Uses selected formatter (`ColorFormatter` or `JsonFormatter`).

### Azure Functions / Core Tools

- Does not add new handlers.
- Does not override host-managed handler strategy.
- Installs `ContextFilter` to enrich records with invocation fields (skipped when `use_record_factory=True`).
- Emits host-level conflict warning checks.

!!! tip
    This split behavior prevents duplicate logs in Azure while still giving rich local developer output.

## host.json Level Conflict Warning

In Azure/Core Tools paths, the library checks `host.json` and warns if host defaults are stricter than your configured level.

Example warning intent:

```text
host.json logLevel.default is set to 'Warning' ... Logs below 'Warning' will be suppressed.
```

Why this matters:

- You may set `level=logging.INFO` in code.
- Host config can still suppress `INFO` lines.
- App settings such as `AzureFunctionsJobHost__logging__logLevel__default`
  can override the deployed `host.json` file.
- Without a warning, this looks like missing logs.

Recommended `host.json` baseline:

```json
{
  "logging": {
    "logLevel": {
      "default": "Information"
    }
  }
}
```

The warning checks both file-based `host.json` and Azure Functions app setting
overrides using the `AzureFunctionsJobHost__logging__logLevel__...` naming
convention. Function-specific overrides such as
`AzureFunctionsJobHost__logging__logLevel__Function__MyFunction=Warning` are
reported as category `Function.MyFunction`.

## Color vs JSON Format Selection

Use `format="color"` when:

- You are iterating locally.
- Humans are primary log consumers.
- You want fast visual scanning of level severity.

Use `format="json"` when:

- Logs feed aggregation systems.
- You need structured indexing and queries.
- You rely on downstream analytics and alerting.

## Using `get_logger()` with Configuration

Typical startup and logger creation:

```python
from azure_functions_logging import get_logger, setup_logging

setup_logging(format="json")
logger = get_logger(__name__)
logger.info("application initialized")
```

`get_logger(name)` returns a `FunctionLogger` wrapper that preserves standard logging ergonomics and supports context binding.

## Advanced Pattern: Custom Formatter Pipeline

For advanced local scenarios you can still combine standard logging with this package:

```python
import logging
from azure_functions_logging import setup_logging

setup_logging(format="json")

custom_handler = logging.StreamHandler()
custom_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))

target = logging.getLogger("custom")
target.addHandler(custom_handler)
target.setLevel(logging.INFO)
```

Guidelines for advanced customization:

- Avoid duplicating handlers on root unless intentional.
- Keep `inject_context(context)` in handlers so context fields remain available.
- Prefer one canonical output format per deployment tier.

## Validation Checklist

Before finalizing configuration:

- Verify setup is called exactly once.
- Verify chosen `format` matches consumer expectations.
- Verify `host.json` does not suppress required levels.
- Verify named logger usage is consistent across modules.
- Verify JSON output can be parsed by your log ingestion tool.

## See Also

- [Getting Started](getting-started.md)
- [Usage Guide](usage.md)
- [Troubleshooting](troubleshooting.md)
- [FAQ](faq.md)
- [API Reference](api.md)
