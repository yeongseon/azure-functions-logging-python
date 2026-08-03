"""Minimal Azure Functions app wiring azure-monitor-opentelemetry + this package.

Demonstrates OpenTelemetry trace correlation (see docs/opentelemetry.md):

- ``configure_azure_monitor()`` is called **before** ``setup_logging()`` so the
  OTel ``LoggingHandler`` exists when context filters (and any PII filters) are
  attached to it.
- ``activate_trace_context=True`` makes ``logging_context`` attach the host's
  W3C trace context, so emitted OTel log records inherit the invocation span's
  ``trace_id`` / ``span_id`` — without this package ever creating a span.

Deploy/run with the Azure Functions Core Tools:

    func start --script-root examples/otel_app

Requires ``pip install "azure-functions-logging[otel]"`` plus
``azure-monitor-opentelemetry`` and an ``APPLICATIONINSIGHTS_CONNECTION_STRING``.
"""

from __future__ import annotations

import json
import logging

import azure.functions as func
from azure.monitor.opentelemetry import configure_azure_monitor

from azure_functions_logging import (
    RedactionFilter,
    get_logger,
    logging_context,
    setup_logging,
)

# 1. Configure the exporter first — this attaches the OTel LoggingHandler to root.
configure_azure_monitor()

# 2. Now decorate the handler that already exists and enable trace activation.
setup_logging(activate_trace_context=True)

# 3. Attach PII redaction to the OTel handler so sensitive extras never export.
_redaction = RedactionFilter()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_redaction)

logger = get_logger(__name__)
app = func.FunctionApp()


@app.route(route="orders", auth_level=func.AuthLevel.ANONYMOUS)
def process_order(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Emit a correlated, redacted, structured log for one invocation."""
    order_id = req.params.get("order_id", "o-demo")

    with logging_context(context):
        # trace_id / span_id are inherited from the host invocation span.
        # `password` is masked by RedactionFilter before it becomes an attribute.
        logger.info(
            "Processing order",
            extra={"order_id": order_id, "password": "should-be-masked"},
        )
        return func.HttpResponse(
            json.dumps({"processed": True, "order_id": order_id}),
            mimetype="application/json",
        )
