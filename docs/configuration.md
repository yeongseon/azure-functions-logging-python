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

- Idempotent initialization: repeated calls do not duplicate handlers or filters.
- Environment-aware behavior: local and Azure runtime paths differ.
- Standard logging compatibility: no custom logging framework required.

!!! note
    In Azure or Core Tools environments, the library intentionally avoids adding handlers to prevent duplicate output.

## Secure production configuration

Redaction is **opt-in**. For Azure Functions host-managed handlers with structured
JSON output, the recommended startup call is:

```python
from azure_functions_logging import JsonFormatter, configure_secure_redaction, setup_logging

setup_logging(functions_formatter=JsonFormatter())
configure_secure_redaction()
```

For standalone execution, call `setup_logging(format="json")`, then
`configure_secure_redaction()`.
The separate preset function preserves the eight-keyword `setup_logging()` ceiling:
privacy policy is not a ninth setup flag. Ordinary setup never changes an explicitly
selected redaction policy; disabling it requires `configure_secure_redaction(enabled=False)`.
The profile does not change host levels or add host handlers. It protects every
handler registered on root or named loggers at call time, including handlers that
receive propagated child-logger records. A logger filter alone cannot cover those
propagated records; a record factory cannot cover `extra` added after creation.

### OpenTelemetry and late handlers

Configure the exporter first, then enable the profile:

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from azure_functions_logging import configure_secure_redaction, setup_logging

configure_azure_monitor()
setup_logging(activate_trace_context=True)
configure_secure_redaction()
```

Keep OTel handlers unformatted so their native attributes remain available.
`activate_trace_context=True` is optional correlation, not a redaction dependency.
Use the optional `[otel]` extra for activation; configure/export telemetry yourself.

Protect a handler created **after** setup before registering it:

```python
import logging
from azure_functions_logging import attach_secure_redaction

handler = logging.StreamHandler()  # or your OTel LoggingHandler
# Add enrichment/flattening filters first, then:
attach_secure_redaction(handler)
logging.getLogger().addHandler(handler)
```

The helper also protects an `IsolatedHandler`'s target, after target-local filters.
For late host handlers you do not create, rerun `configure_secure_redaction()`
once they exist. There is no monkeypatch that automatically protects future
handlers: records emitted before attachment are outside this guarantee.
`use_record_factory=True` covers late-handler **context**, not redaction.

### Ordering and reconfiguration

The secure preset places the package-owned filter last on each handler, after existing
context/flatten filters and before formatting or OTel translation. Thus injected
context attributes and flattened dotted keys are sanitized too. Repeated calls
reuse one package-owned filter, independently of standalone setup idempotency.
Filter-list replacement retains complete snapshots for concurrent logging;
it does not temporarily remove the protection during secure-to-secure setup.
Register enrichment filters before setup, or call `attach_secure_redaction(handler)`
again after adding them. Later filters/formatters that inject new raw data are
outside the protection boundary. Do not reconfigure enrichment concurrently with
logging; explicitly disabling the preset ends protection for subsequent records.

`configure_secure_redaction(enabled=False)` removes only the exact
package-owned secure filter type. Explicit `RedactionFilter` instances and user
subclasses are preserved. This policy selection applies process-wide to current
handlers, independently of the `logger_name=` used for context configuration.

### Fail-closed semantics and compatibility

The secure preset uses `RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS,
fail_closed=True)` with a superset of the existing sensitive keys. Existing keys
already cover Authorization, cookies, Functions keys, API keys and APIM keys.
Secure-only additions cover `proxy_authorization` (proxy credentials),
`shared_access_key`/`shared_access_signature` (Azure access credentials),
`instrumentation_key`/`instrumentationkey` (ingestion identifiers treated
conservatively), `applicationinsights_connection_string`/
`azure_monitor_connection_string` (telemetry configuration), and
`azure_web_jobs_storage`/`azurewebjobsstorage` (storage credentials).
Existing case/camelCase/hyphen normalization and whole dotted-segment matching
apply; the default key set is unchanged.

Conversion/traversal failures mask the affected field as `***`, never its original
object. Opaque objects become guarded, pattern-masked `repr` strings (or `***` if
rendering fails), so a formatter cannot later call their unsafe `str` method.
Mappings, lists, tuples and sets are traversed; non-string keys are sanitized as
well. Sets become lists. Exceptions retain sanitized type/message/traceback fields
and drop raw `exc_info`. A diagnostic conversion failure masks diagnostics; a
message conversion failure emits `[REDACTION FAILED]`, clears arguments and drops
`exc_info`, `exc_text`, and `stack_info`. Ordinary records still return `True`:
redaction failures remain silent and never raise from the filter.

The default `RedactionFilter(fail_closed=False)` deliberately remains fail-open on
conversion/substitution failures so existing applications retain diagnostics and
logging behavior. `setup_logging()` still installs **no** redaction by default.
The secure profile is additive now; changing that default would require a future
minor release with a deprecation/migration discussion, not an announced date.

### Limits and trade-offs

- Secure traversal has a shared **4,096-node per-record** budget (including keys),
  a **10-level** depth limit, and cycle detection. An over-budget collection is
  masked in full; later extras may also be masked. This bounds traversal breadth,
  including huge shallow collections, without touching the compatibility path.
- Text longer than **65,536 characters** is masked in full, not truncated before
  scanning. Arbitrary custom `repr`, mapping methods, and caller regexes can still
  consume time/memory internally; these are not sandboxed or time-limited.
- Numeric/boolean/None observability values, invocation/function/trace/correlation
  IDs, and ordinary non-sensitive strings pass unchanged within these limits.
  Exact sensitive segments are masked, not substrings such as `token_count`,
  `author`, `secretary`, `password_policy`, or `monkey`.
- Curated patterns recognize common bearer/JWT/GitHub tokens, credential
  assignments, connection-string keys and SAS signatures. They cannot identify
  arbitrary unlabelled secrets or PII, encoded/obfuscated credentials, or Unicode
  homograph keys (`ΤΟΚΕΝ`, Turkish dotless-i spellings). They may mask benign
  credential-shaped documentation examples. Add application-specific policies
  where necessary; do not log credentials in the first place.
- Sanitization mutates the shared record; handler isolation is an explicit
  separate choice. Formatters that reread application state, handlers not yet
  protected, direct stdout, and host-generated logs are not covered.
- This is **defence in depth, not a guarantee against arbitrary secrets in free
  text**. Local host capture and in-memory OTel tests do not prove real Azure
  Monitor/Application Insights ingestion behavior.

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
`trace_id`, `span_id`, `cold_start`, `host_instance_id`) are injected at LogRecord creation time. It guarantees
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

### Strategy lifetime and migration

The strategy is process-wide because a record factory affects every logger.
Select it during startup; switch only while logging is quiescent, never during
concurrent invocations. Enabling factory mode removes exact package-owned context
filters across registered loggers and handlers; user subclasses are preserved.
Calling `setup_logging(use_record_factory=False)` (including a bare call) now
restores the preceding factory instead of leaving a mixed factory/filter mode.
Keep passing `use_record_factory=True` on repeated setup if snapshots are needed.

Restoration only occurs when the exact factory installed by this package remains
active. If another library replaces or wraps it, setup raises `RuntimeError`
without removing that library's factory. Tear down that integration in reverse
installation order so our factory is active again, then switch modes. Do not
assign the standard factory blindly: that would discard third-party behavior.

Switching back invalidates package setup bookkeeping, not handlers or formatters.
The next call configures the selected target; rerun setup for other standalone
targets as needed. Azure repeats still discover late host handlers without
adding handlers or changing host levels. Existing records retain fields already
injected; drain queues before switching. Factory mode reserves context keys in
stdlib `extra`; restoring filter mode ends those creation-time reservations.

The local logger-name registry retains first-call handler/level configuration;
the Azure weak-handler registry retains late-handler recovery and formatter
idempotency. Factory ownership is one identity reference, used only to prevent
uninstalling someone else's factory. None stores invocation context.

## Parameter: `extra_context_vars`

`extra_context_vars` is an optional mapping of `field_name -> contextvars.ContextVar`
whose current values `ContextFilter` copies onto each `LogRecord`, alongside the
built-in context fields. Field names must not collide with the built-in fields.
This applies to both `ContextFilter` and factory strategies. Repeated setup with
the same strategy retains its initial mapping; choose fields at startup.

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
