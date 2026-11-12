"""Detect cold start via logging_context."""

from __future__ import annotations

import logging
import types

from azure_functions_logging import get_logger, logging_context, setup_logging


def _make_fake_context(
    invocation_id: str,
    function_name: str = "TimerTrigger1",
) -> types.SimpleNamespace:
    """Build a lightweight object that mimics ``func.Context``."""
    trace_context = types.SimpleNamespace(trace_parent=None)
    return types.SimpleNamespace(
        invocation_id=invocation_id,
        function_name=function_name,
        trace_context=trace_context,
    )


def main() -> None:
    """Show cold_start=true on first invocation, false on subsequent ones."""
    setup_logging(level=logging.DEBUG)
    logger = get_logger(__name__)

    # First invocation - cold start
    ctx1 = _make_fake_context(invocation_id="inv-001")
    with logging_context(ctx1):
        logger.info("First invocation (should show cold_start=true)")

    # Second invocation - warm
    ctx2 = _make_fake_context(invocation_id="inv-002")
    with logging_context(ctx2):
        logger.info("Second invocation (should show cold_start=false)")


if __name__ == "__main__":
    main()
