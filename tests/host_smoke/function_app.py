from __future__ import annotations

import io
import json
import logging

import azure.functions as func

from azure_functions_logging import JsonFormatter, attach_secure_redaction, with_context
from azure_functions_logging._context import ContextFilter

app = func.FunctionApp()


@app.route(route="smoke", auth_level=func.AuthLevel.ANONYMOUS)
@with_context(strict=True)
def smoke(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    return func.HttpResponse(context.function_name)


@app.route(route="smoke-default", auth_level=func.AuthLevel.ANONYMOUS)
@with_context(strict=True)
def smoke_default(
    req: func.HttpRequest,
    context: func.Context = None,  # type: ignore[assignment]
) -> func.HttpResponse:
    return func.HttpResponse(context.function_name)


@app.route(route="smoke-contract", auth_level=func.AuthLevel.ANONYMOUS)
@with_context(strict=True)
def smoke_contract(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    attach_secure_redaction(handler)
    record = logging.getLogger("sdk-host-contract").makeRecord(
        "sdk-host-contract",
        logging.WARNING,
        __file__,
        1,
        "sdk host contract",
        (),
        None,
        extra={"token": "SYNTHETIC_SDK_SECRET"},
    )
    handler.handle(record)
    payload = json.loads(stream.getvalue())
    assert payload["invocation_id"] == context.invocation_id
    assert payload["function_name"] == context.function_name
    assert payload["extra"]["token"] == "***"
    return func.HttpResponse("sdk-contract-ok")
