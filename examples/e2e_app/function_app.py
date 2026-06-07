"""E2E test function app for azure-functions-logging.

Exposes four endpoints:

- GET /api/health            — liveness probe
- GET /api/before            — BEFORE: plain stdlib logging, no context injection
- GET /api/after             — AFTER:  azure-functions-logging with full context
- GET /api/logme             — alias for /api/after (e2e test compat)
"""

from __future__ import annotations

import json
import logging

import azure.functions as func

import azure_functions_logging as afl

# AFTER setup: installs JsonFormatter on host handlers and enables
# invocation_id / function_name / cold_start injection.
afl.setup_logging(functions_formatter=afl.JsonFormatter())

app = func.FunctionApp()


# ── liveness ──────────────────────────────────────────────────────────────


@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps({"status": "ok"}), mimetype="application/json")


# ── BEFORE: plain Python logging, no library context ─────────────────────
#
# Represents what Azure Functions Python logging looks like out of the box.
# Logs appear in Application Insights `traces` table as a plain `message`
# string — no invocation_id, no function_name, no cold_start in customDimensions.


@app.route(route="before", auth_level=func.AuthLevel.ANONYMOUS)
def log_before(req: func.HttpRequest) -> func.HttpResponse:
    """Emit a plain stdlib log — the 'before' state."""
    correlation_id = req.params.get("correlation_id", "before-demo")

    # Plain logging — message only, no structured fields
    logging.info("Processing request correlation_id=%s", correlation_id)
    logging.warning("This log has no invocation_id or function_name context")

    return func.HttpResponse(
        json.dumps({"endpoint": "before", "correlation_id": correlation_id}),
        mimetype="application/json",
    )


# ── AFTER: azure-functions-logging with full context ─────────────────────
#
# Represents the 'after' state. Every log record carries:
#   - invocation_id   (unique per function execution)
#   - function_name   (name of the triggered function)
#   - cold_start      (true on first invocation after scale-out)
#   - correlation_id  (user-supplied extra field, safe from PII leaks)


@app.route(route="after", auth_level=func.AuthLevel.ANONYMOUS)
def log_after(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Emit a structured log — the 'after' state."""
    tokens = afl.inject_context(context)
    logger = afl.get_logger(__name__)

    correlation_id = req.params.get("correlation_id", "after-demo")

    try:
        logger.info(
            "Processing request",
            extra={
                "correlation_id": correlation_id,
                "endpoint": "after",
            },
        )
        logger.warning("Every log carries invocation_id, function_name, and cold_start automatically")

        return func.HttpResponse(
            json.dumps({"endpoint": "after", "correlation_id": correlation_id}),
            mimetype="application/json",
        )
    finally:
        afl.restore_context(tokens)

# ── legacy alias (e2e test compatibility) ────────────────────────────────


@app.route(route="logme", auth_level=func.AuthLevel.ANONYMOUS)
def logme(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Alias for /api/after — keeps existing e2e tests working."""
    return log_after(req, context)
