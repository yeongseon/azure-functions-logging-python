"""Log request correlation fields without exposing credentials.

A local, offline stand-in for an HTTP-triggered handler. It shows which request
values are safe to log (method, route, a validated correlation id) and which are
never logged (the raw headers, including ``Authorization``). All values below are
synthetic; the ``canary-*`` strings only prove that credentials do not leak.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
import types

from azure_functions_logging import get_logger, logging_context, setup_logging

CORRELATION_HEADER = "x-correlation-id"
# Allowlist: only short, plain identifiers are echoed into logs. Anything else
# (too long, spaces, a pasted token, control characters) is ignored.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = get_logger(__name__)


def _make_fake_context(
    invocation_id: str = "11111111-2222-3333-4444-555555555555",
    function_name: str = "OrdersHttp",
    trace_parent: str = "00-abcdef1234567890abcdef1234567890-1234567890abcdef-01",
) -> types.SimpleNamespace:
    """Build a lightweight object that mimics ``func.Context``."""
    return types.SimpleNamespace(
        invocation_id=invocation_id,
        function_name=function_name,
        trace_context=types.SimpleNamespace(trace_parent=trace_parent),
    )


def _make_fake_request(headers: Mapping[str, str]) -> types.SimpleNamespace:
    """Build a lightweight object that mimics ``func.HttpRequest``."""
    return types.SimpleNamespace(method="POST", url="http://localhost/api/orders", headers=headers)


def safe_correlation_id(headers: Mapping[str, str], fallback: str) -> str:
    """Return the caller's correlation id only if it is a plain identifier.

    Falls back to the invocation id so every request is still correlatable.
    """
    value = headers.get(CORRELATION_HEADER, "")
    return value if _SAFE_ID.fullmatch(value) else fallback


def handle_request(req: types.SimpleNamespace, context: types.SimpleNamespace) -> int:
    """Handle one request and return an HTTP status code."""
    with logging_context(context):
        correlation_id = safe_correlation_id(req.headers, fallback=context.invocation_id)
        # Bind only allowlisted fields. Never log ``req.headers`` or the body.
        request_logger = logger.bind(
            correlation_id=correlation_id, method=req.method, route="orders"
        )
        request_logger.info("request received")
        request_logger.info("request completed", status_code=200)
        return 200


def main() -> None:
    """Show correlated request logs for a request that carries credentials."""
    setup_logging(format="json", level=logging.DEBUG)
    headers = {
        CORRELATION_HEADER: "order-7f3a",
        "Authorization": "Bearer canary-bearer-token-0000",  # synthetic, never logged
        "x-api-key": "canary-api-key-0000",  # synthetic, never logged
    }
    handle_request(_make_fake_request(headers), _make_fake_context())


if __name__ == "__main__":
    main()
