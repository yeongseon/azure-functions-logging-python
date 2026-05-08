"""E2E test function app for azure-functions-logging."""

from __future__ import annotations

import json
import logging

import azure.functions as func

import azure_functions_logging as afl

afl.setup_logging()

app = func.FunctionApp()


@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps({"status": "ok"}), mimetype="application/json")


@app.route(route="logme", auth_level=func.AuthLevel.ANONYMOUS)
def logme(req: func.HttpRequest) -> func.HttpResponse:
    """Invoke this endpoint to trigger structured JSON logging."""
    logger = afl.get_logger(__name__)
    # Inject Azure Functions invocation context if available
    ctx = getattr(req, "__func_context__", None)
    if ctx is not None:
        afl.inject_context(ctx)

    correlation_id = req.params.get("correlation_id", "e2e-test")
    logger.info("e2e log entry", extra={"correlation_id": correlation_id})
    logging.info("e2e stdlib log: correlation_id=%s", correlation_id)

    return func.HttpResponse(
        json.dumps({"logged": True, "correlation_id": correlation_id}),
        mimetype="application/json",
    )
