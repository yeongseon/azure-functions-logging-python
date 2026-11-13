"""Show when invocation context is active around sync and async generators.

Everything here is fake and offline: invocation ids are made up and no Azure
Functions host is involved. Run ``python examples/generator_context.py``.

The rule the three demos illustrate: context applies while the generator body
*runs* (each resume), not where the generator object was created, and the
caller's own context is restored at every ``yield``. Context is carried by
``contextvars`` on the thread that resumes the generator; this does not make
arbitrary background threads inherit it (use ``propagate_context()`` for that).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
import logging
import types

from azure_functions_logging import get_logger, logging_context, setup_logging, with_context

LOGGER_NAME = "examples.generator_context"

logger = get_logger(LOGGER_NAME)


def _fake_context(invocation_id: str) -> types.SimpleNamespace:
    """Build a lightweight object that mimics ``func.Context`` (fake ids only)."""
    return types.SimpleNamespace(invocation_id=invocation_id, function_name="StreamDemo")


@with_context
def stream_chunks(context: types.SimpleNamespace, fail_after: int | None = None) -> Iterator[int]:
    """Decorated sync generator: each resume runs under ``context``."""
    for chunk in range(1, 4):
        logger.info("producer yielding", chunk=chunk)
        if fail_after == chunk:
            raise RuntimeError("producer failed")
        yield chunk


@with_context
async def astream_chunks(context: types.SimpleNamespace) -> AsyncIterator[int]:
    """Decorated async generator with the same contract."""
    for chunk in range(1, 3):
        logger.info("async producer yielding", chunk=chunk)
        yield chunk


def sync_demo(fail_after: int | None = None) -> None:
    """Producer and consumer log under different invocations; the caller's is restored."""
    with logging_context(_fake_context("outer-request")):
        try:
            for chunk in stream_chunks(_fake_context("stream-invocation"), fail_after):
                logger.info("consumer received", chunk=chunk)  # caller's context
        except RuntimeError:
            logger.info("consumer saw the failure")  # still the caller's context
        logger.info("after iteration")  # caller's context restored
    logger.info("outside any context")  # no invocation context at all


async def async_demo() -> None:
    """Async counterpart of :func:`sync_demo`."""
    with logging_context(_fake_context("outer-request")):
        async for chunk in astream_chunks(_fake_context("stream-invocation")):
            logger.info("async consumer received", chunk=chunk)
        logger.info("after async iteration")
    logger.info("outside any context")


def scope_restoration_counterpart() -> None:
    """A plain generator is NOT bound to the scope it was created in."""

    def plain() -> Iterator[int]:
        logger.info("plain generator body runs")
        yield 1

    with logging_context(_fake_context("created-here")):
        iterator = plain()  # created inside the scope, but nothing has run yet

    next(iterator)  # the body runs now, outside the scope: no invocation context
    iterator.close()


def main() -> None:
    """Run all demos and print their JSON records."""
    setup_logging(format="json", level=logging.INFO, logger_name=LOGGER_NAME)
    sync_demo()
    sync_demo(fail_after=2)
    asyncio.run(async_demo())
    scope_restoration_counterpart()


if __name__ == "__main__":
    main()
