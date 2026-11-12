"""Inject invocation context into log records."""

from __future__ import annotations

import logging
import types

from azure_functions_logging import get_logger, logging_context, setup_logging


def _make_fake_context(
    invocation_id: str = "abc-123",
    function_name: str = "HttpTrigger1",
    trace_parent: str = ("00-abcdef1234567890abcdef1234567890-1234567890abcdef-01"),
) -> types.SimpleNamespace:
    """Build a lightweight object that mimics ``func.Context``."""
    trace_context = types.SimpleNamespace(trace_parent=trace_parent)
    return types.SimpleNamespace(
        invocation_id=invocation_id,
        function_name=function_name,
        trace_context=trace_context,
    )


def main() -> None:
    """Show how logging_context adds invocation metadata to every log line."""
    setup_logging(level=logging.DEBUG)
    logger = get_logger(__name__)

    context = _make_fake_context()
    with logging_context(context):  # restores the previous context on exit
        logger.info("Handling request")
        logger.warning("Slow upstream call")


if __name__ == "__main__":
    main()
