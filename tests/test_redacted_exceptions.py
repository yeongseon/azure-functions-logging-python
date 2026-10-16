from __future__ import annotations

import io
import json
import logging

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor

from azure_functions_logging import JsonFormatter, RedactionFilter

_SYNTHETIC_SECRET = "REVIEWOPAQUE123456"


def _raise_secret_error() -> None:
    try:
        raise KeyError(f"password={_SYNTHETIC_SECRET}")
    except KeyError as cause:
        raise ValueError(f"token={_SYNTHETIC_SECRET}") from cause


def test_json_formatter_preserves_sanitized_chained_exception() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    logger = logging.Logger("redacted-json-exception", logging.INFO)
    logger.addHandler(handler)

    try:
        _raise_secret_error()
    except ValueError:
        logger.exception("operation failed")

    payload = json.loads(stream.getvalue())
    assert payload["exception"] is not None
    assert "ValueError" in payload["exception"]
    assert "Traceback" in payload["exception"]
    assert _SYNTHETIC_SECRET not in stream.getvalue()


def test_json_formatter_preserves_sanitized_cached_exception_text() -> None:
    record = logging.LogRecord("cached", logging.ERROR, __file__, 1, "failed", (), None)
    record.exc_text = f"ValueError: password={_SYNTHETIC_SECRET}"
    redaction = RedactionFilter()

    redaction.filter(record)
    first = JsonFormatter().format(record)
    second = JsonFormatter().format(record)

    assert json.loads(first)["exception"] == "ValueError: password=***"
    assert json.loads(second)["exception"] == "ValueError: password=***"
    assert _SYNTHETIC_SECRET not in first + second


def test_otel_handler_preserves_sanitized_exception_attributes() -> None:
    exporter = InMemoryLogExporter()  # type: ignore[no-untyped-call]
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(logger_provider=provider)
    handler.addFilter(RedactionFilter(patterns=[_SYNTHETIC_SECRET]))
    logger = logging.Logger("redacted-otel-exception", logging.INFO)
    logger.addHandler(handler)

    try:
        _raise_secret_error()
    except ValueError:
        logger.exception("operation failed")

    attributes = exporter.get_finished_logs()[0].log_record.attributes
    assert attributes is not None
    assert attributes["exception.type"] == "ValueError"
    assert "token=***" in str(attributes["exception.message"])
    assert "Traceback" in str(attributes["exception.stacktrace"])
    assert _SYNTHETIC_SECRET not in "".join(str(value) for value in attributes.values())
    handler.close()
    provider.shutdown()
