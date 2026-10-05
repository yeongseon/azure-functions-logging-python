from __future__ import annotations

import azure.functions as func

from azure_functions_logging import with_context

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
