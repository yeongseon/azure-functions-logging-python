"""OpenTelemetry log-correlation spike, kept as a regression guard (issue #253).

The original spike proved that attaching the host's W3C trace context lets an
OpenTelemetry ``LoggingHandler`` stamp emitted log records with the host span's
``trace_id`` / ``span_id`` — without this package ever creating, recording, or
exporting a span. Per #253 the spike itself is retained here so the pinned
behaviour (including its known thread-boundary limitation) cannot silently
regress.

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

    logger = logging.getLogger("afl.otel.spike")
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


def test_spike_sync_record_inherits_host_span(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    logger, exporter = otel_logger
    with logging_context(_make_context(), activate_trace_context=True):
        logger.info("hello")
    record = _only_record(exporter)
    assert format(record.trace_id, "032x") == _TRACE_ID
    assert format(record.span_id, "016x") == _PARENT_ID


def test_spike_correlation_survives_await(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    logger, exporter = otel_logger

    async def handler() -> None:
        with logging_context(_make_context(), activate_trace_context=True):
            await asyncio.sleep(0)
            logger.info("after await")

    asyncio.run(handler())
    record = _only_record(exporter)
    assert format(record.span_id, "016x") == _PARENT_ID


def test_spike_gather_isolates_concurrent_contexts(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
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
    # Each concurrent task's record carries only its own host span — no bleed.
    assert by_message == {"a": _PARENT_ID, "b": _PARENT_ID_B}


def test_spike_thread_boundary_loses_correlation(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    """Known limitation: OTel runtime context is contextvar-based, so worker
    threads spawned via ``ThreadPoolExecutor`` do NOT inherit the host span.
    Pinned as a regression guard (span_id == 0 in the spawned thread)."""
    logger, exporter = otel_logger

    with logging_context(_make_context(), activate_trace_context=True):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(logger.info, "from thread").result()

    record = _only_record(exporter)
    assert record.span_id == 0


def test_spike_nested_contexts_restore_outer_span(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
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


def test_spike_exception_path_detaches_context(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    logger, exporter = otel_logger

    with pytest.raises(ValueError):
        with logging_context(_make_context(), activate_trace_context=True):
            raise ValueError("boom")

    # After the failing block the host span must be detached: a later record
    # emitted outside any context is uncorrelated.
    logger.info("after")
    record = _only_record(exporter)
    assert record.span_id == 0


def test_spike_no_context_is_uncorrelated(
    otel_logger: tuple[logging.Logger, InMemoryLogRecordExporter],
) -> None:
    logger, exporter = otel_logger
    logger.info("orphan")
    record = _only_record(exporter)
    assert record.span_id == 0
