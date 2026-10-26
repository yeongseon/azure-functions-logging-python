"""Real OTel export, isolation, capture, and concurrent reconfiguration evidence."""

from concurrent.futures import ThreadPoolExecutor
import io
import logging
from threading import Barrier
from types import SimpleNamespace

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
import pytest
from test_secure_setup import CANARY, InspectFormatter, clean_setup

from azure_functions_logging import (
    AttributeFlattenFilter,
    IsolatedHandler,
    attach_secure_redaction,
    configure_secure_redaction,
    logging_context,
    setup_logging,
)

__all__ = ["clean_setup"]


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("isolated", [False, True])
def test_otel_exports_only_sanitized_child_records(late: bool, isolated: bool) -> None:
    # Given
    provider = LoggerProvider()
    exporter = InMemoryLogRecordExporter.__new__(InMemoryLogRecordExporter)
    getattr(exporter, "__init__")()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    target = LoggingHandler(logger_provider=provider)
    handler = IsolatedHandler(target) if isolated else target
    target.addFilter(AttributeFlattenFilter())
    root = logging.getLogger()
    if late:
        setup_logging()
        configure_secure_redaction()
        attach_secure_redaction(handler)
        root.addHandler(handler)
    else:
        root.addHandler(handler)
        setup_logging()
        configure_secure_redaction()
    context = SimpleNamespace(
        invocation_id="inv-42",
        function_name="secure_fn",
        trace_context=SimpleNamespace(trace_parent="00-" + "a" * 32 + "-" + "b" * 16 + "-01"),
    )
    # When
    try:
        with logging_context(context, activate_trace_context=True):
            try:
                raise ValueError(f"password={CANARY}")
            except ValueError:
                logging.getLogger("secure.export.child").exception(
                    "Bearer %s", CANARY, extra={"order": {"token": CANARY, "count": 7}}
                )
        # Then
        records = exporter.get_finished_logs()
        assert len(records) == 1
        record = records[0].log_record
        attributes = dict(record.attributes or {})
        assert CANARY not in repr((record.body, attributes))
        assert record.body == "Bearer ***"
        assert attributes["order.token"] == "***"
        assert attributes["order.count"] == 7
        assert "ValueError" in str(attributes["exception.type"])
        assert "Traceback" in str(attributes["exception.stacktrace"])
        assert record.trace_id == int("a" * 32, 16)
        assert record.span_id == int("b" * 16, 16)
    finally:
        root.removeHandler(handler)
        handler.close()
        provider.shutdown()


def test_caplog_text_and_records_are_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    # Given
    logging.getLogger().addHandler(caplog.handler)
    setup_logging()
    configure_secure_redaction()
    # When
    logging.getLogger("secure.capture.child").warning(
        "password=%s",
        CANARY,
        extra={"exception.message": f"token={CANARY}", "exception.stacktrace": f"Bearer {CANARY}"},
    )
    # Then
    assert CANARY not in caplog.text
    assert CANARY not in repr(caplog.records[-1].__dict__)


def test_concurrent_secure_reconfiguration_never_opens_filter_gap() -> None:
    # Given
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(InspectFormatter())
    logging.getLogger().addHandler(handler)
    setup_logging()
    configure_secure_redaction()
    barrier = Barrier(9)

    def emit() -> None:
        barrier.wait()
        for _ in range(100):
            logging.getLogger("secure.concurrent.child").warning("token=%s", CANARY)

    def configure() -> None:
        barrier.wait()
        for _ in range(100):
            configure_secure_redaction()

    # When
    with ThreadPoolExecutor(max_workers=9) as pool:
        futures = [pool.submit(emit) for _ in range(8)] + [pool.submit(configure)]
        for future in futures:
            future.result(timeout=30)
    # Then
    assert CANARY not in stream.getvalue()
    assert len(stream.getvalue().splitlines()) == 800
