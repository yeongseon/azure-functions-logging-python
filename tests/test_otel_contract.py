"""End-to-end OpenTelemetry log-correlation contract (issues #253, #437).

These tests are the **behavioural contract** for
:func:`azure_functions_logging._otel.activated_trace_context` proven through a
real OpenTelemetry ``LoggingHandler`` and in-memory exporter — i.e. the same
path a production app exercises. They complement the unit-level contract in
``tests/test_otel.py`` (which drives ``activated_trace_context`` directly) by
asserting the *observable* result: the ``trace_id`` / ``span_id`` actually
stamped onto emitted log records.

Each test maps to a documented invariant of ``activated_trace_context``:

* a valid host span is attached and inherited by emitted records;
* correlation survives ``await`` and stays isolated across concurrent tasks;
* the context is always detached on exit (normal and exceptional);
* a record emitted with no active context is uncorrelated (``span_id == 0``);
* an already-active **real local** span is never overwritten by the host span;
* an invalid/no-op host span context is not attached;
* nested host activations restore the outer host span on exit;
* the contextvar boundary means worker threads do not inherit correlation.

The package never creates, records, or exports a span itself — it only
*attaches* the remote span context extracted from the host ``traceparent``.

These tests require the OpenTelemetry SDK. They skip cleanly when it is absent,
so the base install stays zero-dependency.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

pytest.importorskip("opentelemetry.sdk._logs")

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler  # noqa: E402
from opentelemetry.sdk._logs.export import (  # noqa: E402
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)

from azure_functions_logging import logging_context  # noqa: E402

# W3C traceparent fixtures. ``_PARENT_ID`` is the host span-id every correlated
# record must inherit.
_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_ID = "00f067aa0ba902b7"
_TRACEPARENT = f"00-{_TRACE_ID}-{_PARENT_ID}-01"

# A second, distinct host span for concurrency-isolation assertions.
_TRACE_ID_B = "0af7651916cd43dd8448eb211c80319c"
_PARENT_ID_B = "b7ad6b7169203331"
_TRACEPARENT_B = f"00-{_TRACE_ID_B}-{_PARENT_ID_B}-01"

# An all-zero traceparent extracts to an invalid (no-op) span context, which
# must NOT be attached — doing so would break the trace tree.
_INVALID_TRACEPARENT = "00-00000000000000000000000000000000-0000000000000000-00"


def _make_context(trace_parent: str | None = _TRACEPARENT) -> SimpleNamespace:
    return SimpleNamespace(
        invocation_id="inv-1",
        function_name="fn-a",
        trace_context=SimpleNamespace(trace_parent=trace_parent, trace_state=None),
    )


@pytest.fixture
def otel_logger() -> Iterator[tuple[logging.Logger, InMemoryLogRecordExporter]]:
    """A logger wired to an in-memory OTel ``LoggingHandler``."""
    provider = LoggerProvider()
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(logger_provider=provider)

    logger = logging.getLogger("afl.otel.contract")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    try:
        yield logger, exporter
    finally:
        logger.removeHandler(handler)
        provider.shutdown()


def _only_record(exporter: InMemoryLogRecordExporter) -> Any:
    logs = exporter.get_finished_logs()
    assert len(logs) == 1
    return logs[0].log_record


def test_valid_host_span_is_inherited_by_sync_record(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: a valid host ``traceparent`` is attached, so a record emitted
    inside the activation inherits the host ``trace_id`` and ``span_id``."""
    logger, exporter = otel_logger
    with logging_context(_make_context(), activate_trace_context=True):
        logger.info("hello")
    record = _only_record(exporter)
    assert format(record.trace_id, "032x") == _TRACE_ID
    assert format(record.span_id, "016x") == _PARENT_ID


def test_correlation_survives_await(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: activation is contextvar-based, so it survives ``await``."""
    logger, exporter = otel_logger

    async def handler() -> None:
        with logging_context(_make_context(), activate_trace_context=True):
            await asyncio.sleep(0)
            logger.info("after await")

    asyncio.run(handler())
    record = _only_record(exporter)
    assert format(record.span_id, "016x") == _PARENT_ID


def test_concurrent_tasks_keep_isolated_host_spans(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: concurrent ``asyncio`` tasks each see only their own host
    span — no cross-task context bleed."""
    logger, exporter = otel_logger

    async def emit(trace_parent: str, message: str) -> None:
        with logging_context(_make_context(trace_parent), activate_trace_context=True):
            await asyncio.sleep(0)
            logger.info(message)

    async def run() -> None:
        await asyncio.gather(
            emit(_TRACEPARENT, "a"),
            emit(_TRACEPARENT_B, "b"),
        )

    asyncio.run(run())

    by_message = {
        rec.log_record.body: format(rec.log_record.span_id, "016x")
        for rec in exporter.get_finished_logs()
    }
    assert by_message == {"a": _PARENT_ID, "b": _PARENT_ID_B}


def test_worker_thread_does_not_inherit_correlation(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract (documented limitation): OTel runtime context is
    contextvar-based, so worker threads spawned via ``ThreadPoolExecutor`` do
    NOT inherit the host span. Records there fall back to ``span_id == 0``."""
    logger, exporter = otel_logger

    with logging_context(_make_context(), activate_trace_context=True):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(logger.info, "from thread").result()

    record = _only_record(exporter)
    assert record.span_id == 0


def test_nested_host_activation_restores_outer_span(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: a nested host activation overrides the outer host span while
    active, then restores the outer host span (LIFO detach) on exit."""
    logger, exporter = otel_logger

    with logging_context(_make_context(_TRACEPARENT), activate_trace_context=True):
        with logging_context(_make_context(_TRACEPARENT_B), activate_trace_context=True):
            logger.info("inner")
        logger.info("outer")

    spans = {
        rec.log_record.body: format(rec.log_record.span_id, "016x")
        for rec in exporter.get_finished_logs()
    }
    assert spans == {"inner": _PARENT_ID_B, "outer": _PARENT_ID}


def test_context_is_detached_after_exception(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: the host context is always detached on exit, including when
    the block raises — a later record outside any context is uncorrelated."""
    logger, exporter = otel_logger

    with pytest.raises(ValueError):
        with logging_context(_make_context(), activate_trace_context=True):
            raise ValueError("boom")

    logger.info("after")
    record = _only_record(exporter)
    assert record.span_id == 0


def test_record_without_active_context_is_uncorrelated(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: outside any activation a record has no host span
    (``span_id == 0``)."""
    logger, exporter = otel_logger
    logger.info("orphan")
    record = _only_record(exporter)
    assert record.span_id == 0


def test_invalid_host_span_context_is_not_attached(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: an all-zero (invalid/no-op) extracted span context must NOT be
    attached — the record stays uncorrelated rather than parented to an invalid
    context that would break the trace tree."""
    logger, exporter = otel_logger
    with logging_context(_make_context(_INVALID_TRACEPARENT), activate_trace_context=True):
        logger.info("invalid host span")
    record = _only_record(exporter)
    assert record.span_id == 0


def test_active_real_local_span_is_not_overwritten(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Contract: when a real local span is already active (e.g. worker
    auto-instrumentation or the user's own ``start_as_current_span``), the host
    activation must leave it untouched — the record inherits the LOCAL span, not
    the host's non-recording remote span."""
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider

    logger, exporter = otel_logger
    # A real SDK-backed tracer produces a *valid* local span; the default
    # (no-op) tracer would produce span_id 0 and be treated as "no local span".
    tracer = TracerProvider().get_tracer("afl.otel.contract.test")

    with tracer.start_as_current_span("local-span") as local_span:
        local_span_id = format(local_span.get_span_context().span_id, "016x")
        with logging_context(_make_context(), activate_trace_context=True):
            logger.info("under local span")

    record = _only_record(exporter)
    # The real local span wins — the host span-id must NOT appear.
    assert format(record.span_id, "016x") == local_span_id
    assert format(record.span_id, "016x") != _PARENT_ID
