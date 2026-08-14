# Example: Logger Name Targeting

This example demonstrates when and how to use `setup_logging(logger_name=...)` with named logger hierarchies.

## When to Use `logger_name`

Use named targeting when you need:

- Isolated configuration for a subsystem.
- Controlled migration from legacy logging setup.
- Separation between app and library logger behavior.

For many projects, root setup remains the simplest baseline.

## Baseline Named Setup

```python
import logging
from azure_functions_logging import get_logger, setup_logging

setup_logging(level=logging.INFO, format="json", logger_name="payments")

payments_api_logger = get_logger("payments.api")
payments_worker_logger = get_logger("payments.worker")
inventory_logger = get_logger("inventory")

payments_api_logger.info("api event")
payments_worker_logger.info("worker event")
inventory_logger.info("inventory event")
```

## What Happens

Expected behavior with this setup:

- `payments.*` hierarchy uses configured pipeline.
- Non-descendant loggers may not behave identically unless root is configured too.

## Hierarchy Reminder

Logger names are dot-scoped:

- `payments` is parent.
- `payments.api` and `payments.worker` are children.
- `inventory` is separate hierarchy.

This hierarchy determines propagation and effective configuration.

## Practical Pattern: Bounded Migration

If migrating a large app:

1. Configure one subsystem with `logger_name="payments"`.
2. Move modules under `payments.*` names.
3. Validate output and field quality.
4. Expand scope or move to root config later.

## Function Example with Named Logger

```python
import azure.functions as func
from azure_functions_logging import JsonFormatter, get_logger, logging_context, setup_logging

setup_logging(functions_formatter=JsonFormatter(), logger_name="payments")
logger = get_logger("payments.http")

app = func.FunctionApp()


@app.route(route="payments")
def payments(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        request_logger = logger.bind(route="/payments", method=req.method)
        request_logger.info("payments request")
        return func.HttpResponse("ok")
```

## In Application Insights

After deploying and requesting `/api/payments`, query the `traces` table filtered by logger name. The named-logger identity is preserved in `customDimensions.logger` (see the [deployment query guide](../deployment.md#inspect-traces-and-requests) for the raw-`message` variant).

```kql
traces
| where customDimensions.logger == "payments.http"
| project timestamp, message, customDimensions.logger, customDimensions.invocation_id, customDimensions.route
| order by timestamp asc
```

Expected result — only the targeted `payments.*` hierarchy appears:

| timestamp | message | logger | invocation_id | route |
| --- | --- | --- | --- | --- |
| 2026-03-14T10:20:30.12Z | payments request | `payments.http` | `abc-123-def` | `/payments` |

Filtering on `customDimensions.logger` lets you build a dashboard scoped to one subsystem while other hierarchies (e.g. `inventory`) stay out of view.

> If your pipeline leaves the JSON inside the `message` column instead, use `extend payload = parse_json(message)` and read `payload.logger`.

## Common Pitfalls

- Mixing unrelated logger names and expecting same behavior.
- Assuming `logger_name` setup reconfigures all existing loggers.
- Combining root and named setup without a clear propagation strategy.

## Validation Steps

Use these checks after named setup:

1. Confirm logger names used by modules.
2. Confirm parent-child hierarchy matches expectations.
3. Confirm output appears once (no duplicates).
4. Confirm context fields appear where expected.
5. Confirm non-target hierarchies are intentionally configured.

## Root vs Named Decision Guide

Choose root when:

- App is cohesive and single pipeline is acceptable.
- You want simplest setup and minimal cognitive overhead.

Choose named when:

- Multi-service codebase needs staged adoption.
- One domain requires stricter or separate behavior.
- You are migrating legacy logging incrementally.

## Example: Dependency Noise Suppression

Even with named setup, standard logger controls still apply:

```python
import logging

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
```

## Related Docs

- [Configuration](../configuration.md)
- [Usage Guide](../usage.md)
- [Troubleshooting](../troubleshooting.md)
