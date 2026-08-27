"""E2E test function app for azure-functions-logging.

Exposes these endpoints:

- GET /api/health            — liveness probe
- GET /api/before            — BEFORE: plain stdlib logging, no context injection
- GET /api/after             — AFTER:  azure-functions-logging with full context
- GET /api/logme             — alias for /api/after (e2e test compat)
- GET /api/correlation       — emits records that certify correlation claims:
                               two main-thread records share one invocation_id,
                               and a background thread without propagate_context
                               loses it (negative control).
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import threading

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


@app.route(route="version", auth_level=func.AuthLevel.ANONYMOUS)
def version(req: func.HttpRequest) -> func.HttpResponse:
    """Report the installed package version so e2e can certify the candidate.

    Proves the deployed host is running the exact wheel bundled by CI rather
    than whatever is currently published on PyPI.
    """
    installed = importlib.metadata.version("azure-functions-logging")
    return func.HttpResponse(
        json.dumps({"version": installed}), mimetype="application/json"
    )

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
#   - correlation_id  (user-supplied extra field — do not log PII values here)


@app.route(route="after", auth_level=func.AuthLevel.ANONYMOUS)
def log_after(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Emit a structured log — the 'after' state."""
    tokens = afl.inject_context(context)
    logger = afl.get_logger(__name__)

    correlation_id = req.params.get("correlation_id", "after-demo")

    try:
        logger.info(
            # Include correlation_id in the message string so it is searchable
            # regardless of ingestion shape (customDimensions or raw message column).
            "Processing request correlation_id=%s",
            correlation_id,
            extra={
                "correlation_id": correlation_id,
                "endpoint": "after",
            },
        )
        logger.warning(
            "Every log carries invocation_id, function_name, and cold_start automatically"
        )

        return func.HttpResponse(
            json.dumps({"endpoint": "after", "correlation_id": correlation_id}),
            mimetype="application/json",
        )
    finally:
        afl.restore_context(tokens)


# ── legacy alias (e2e test compatibility) ────────────────────────────────


@app.route(route="logme", auth_level=func.AuthLevel.ANONYMOUS)
def logme(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Backward-compatible alias — keeps existing e2e tests working.

    Returns {"logged": true, "correlation_id": ...} to preserve the
    historical response shape expected by e2e tests and the deployment guide.
    """
    tokens = afl.inject_context(context)
    logger = afl.get_logger(__name__)
    correlation_id = req.params.get("correlation_id", "logme-demo")
    try:
        logger.info(
            "Processing request correlation_id=%s",
            correlation_id,
            extra={"correlation_id": correlation_id, "endpoint": "logme"},
        )
        return func.HttpResponse(
            json.dumps({"logged": True, "correlation_id": correlation_id}),
            mimetype="application/json",
        )
    finally:
        afl.restore_context(tokens)


# ── correlation certification ────────────────────────────────────────────
#
# Emits records that let the host-boot matrix smoke assert the claims made in
# docs/how-correlation-works.md against a real func host:
#
#   1. invocation_id on a bound record parses as a UUID (§1–§2).
#   2. Two records from the same invocation share one invocation_id (§2).
#   3. A background thread WITHOUT propagate_context loses the invocation_id
#      (§4, negative control) — proving the contextvars boundary is real.
#
# Every record carries a stable "marker" extra field so the assertion script can
# locate the exact lines regardless of ordering or interleaving.


@app.route(route="correlation", auth_level=func.AuthLevel.ANONYMOUS)
def correlation(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Emit correlation-certification records for the host-boot smoke."""
    logger = afl.get_logger(__name__)
    tokens = afl.inject_context(context)
    try:
        # (1) + (2): two bound records on the request thread — same invocation_id,
        # which must be a valid UUID.
        logger.info("afl correlation certify", extra={"marker": "corr-main-1"})
        logger.info("afl correlation certify", extra={"marker": "corr-main-2"})

        # (3) negative control: a background thread with NO propagate_context.
        # Its record must NOT carry the invocation_id.
        def _unpropagated() -> None:
            logger.warning(
                "afl correlation certify", extra={"marker": "corr-thread-unpropagated"}
            )

        thread = threading.Thread(target=_unpropagated)
        thread.start()
        thread.join()

        return func.HttpResponse(
            json.dumps({"endpoint": "correlation", "invocation_id": context.invocation_id}),
            mimetype="application/json",
        )
    finally:
        afl.restore_context(tokens)
