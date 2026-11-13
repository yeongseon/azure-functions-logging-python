"""Nested, request-local context binding that cleans up after itself.

Run ``python examples/nested_context_binding.py``. A warm Azure Functions worker
handles many invocations in one process, so scoped context must not outlive its
request. The demo uses fake ids and a plain ``logging.Logger``:

* ``logging_context(ctx)`` scopes the invocation fields (``invocation_id`` ...).
* ``bind_context(...)`` scopes your own fields. The outer scope sets a stable
  ``request_id``; an inner scope adds ``item_id`` and overrides ``stage``, and both
  are restored when the inner block exits.
* ``get_logger(...).bind(...)`` is different: its fields belong to the *logger
  object* and travel wherever that object is used, regardless of scope.
* Sequential requests and concurrent asyncio tasks never see each other's fields.
"""

from __future__ import annotations

import asyncio
import logging
import types

from azure_functions_logging import (
    bind_context,
    get_logger,
    logging_context,
    setup_logging,
)

LOGGER_NAME = "examples.nested_context_binding"

logger = logging.getLogger(LOGGER_NAME)  # a plain stdlib logger: no wrapper required


def _fake_context(invocation_id: str) -> types.SimpleNamespace:
    """Build a lightweight object that mimics ``func.Context`` (fake ids only)."""
    return types.SimpleNamespace(invocation_id=invocation_id, function_name="NestedDemo")


def process_item(item_id: str) -> None:
    """Inner scope: adds ``item_id``, overrides ``stage``; both vanish on exit."""
    with bind_context(item_id=item_id, stage="item"):
        logger.info("item processed")
    logger.info("after inner scope")  # item_id gone, stage back to "request"


def handle_request(request_id: str, tenant: str) -> None:
    """One invocation: outer scope with a stable correlation attribute."""
    with logging_context(_fake_context(f"inv-{request_id}")):
        with bind_context(request_id=request_id, tenant=tenant, stage="request"):
            logger.info("request started")
            process_item("item-1")
            logger.info("request finished")


async def handle_request_async(request_id: str, tenant: str) -> None:
    """Async variant; yields to the event loop so tasks interleave."""
    with logging_context(_fake_context(f"inv-{request_id}")):
        with bind_context(request_id=request_id, tenant=tenant, stage="request"):
            logger.info("async request started")
            await asyncio.sleep(0)
            logger.info("async request finished")


async def concurrent_requests() -> None:
    """Two interleaved tasks: each keeps only its own bindings."""
    await asyncio.gather(
        handle_request_async("r-3", "tenant-c"),
        handle_request_async("r-4", "tenant-d"),
    )


def bind_versus_scope() -> None:
    """A logger-bound field follows the logger object; a scoped field follows the scope."""
    bound = get_logger(LOGGER_NAME).bind(source="logger-bound")
    with bind_context(source_scope="scope-bound"):
        bound.info("inside the scope")  # carries both
    bound.info("outside the scope")  # still carries ``source``; ``source_scope`` is gone


def main() -> None:
    """Run the demos in one process, as a warm worker would."""
    setup_logging(format="json", level=logging.INFO, logger_name=LOGGER_NAME)
    handle_request("r-1", "tenant-a")
    handle_request("r-2", "tenant-b")  # unrelated request: nothing from r-1 remains
    asyncio.run(concurrent_requests())
    bind_versus_scope()


if __name__ == "__main__":
    main()
