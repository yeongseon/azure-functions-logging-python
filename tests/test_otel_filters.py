"""Verification tests for filter attachment on OpenTelemetry logging handlers (#259).

In OpenTelemetry logging mode the entire ``extra`` mapping is emitted as log
**attributes**, so ``RedactionFilter`` (PII) and ``SamplingFilter`` (noise) must
be attached to the OTel ``LoggingHandler`` to have any effect. These tests prove
that package filters actually mutate/drop records flowing through a real OTel
``LoggingHandler`` before they are exported.

The required call order is ``configure_azure_monitor()`` (which attaches the OTel
handler) **before** ``setup_logging()`` (which decorates handlers that already
exist). We simulate the OTel handler directly with the SDK's in-memory exporter,
so no Azure Monitor connection is needed.

All tests skip cleanly when ``opentelemetry-sdk`` is absent, keeping the base
install zero-dependency.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

import pytest

pytest.importorskip("opentelemetry.sdk._logs")

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler  # noqa: E402

try:  # exporter was renamed; logs API is not yet stable
    from opentelemetry.sdk._logs.export import (  # noqa: E402
        InMemoryLogRecordExporter as _InMemoryExporter,
    )
except ImportError:  # pragma: no cover - depends on installed SDK version
    from opentelemetry.sdk._logs.export import (  # noqa: E402
        InMemoryLogExporter as _InMemoryExporter,
    )

from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor  # noqa: E402

from azure_functions_logging import (  # noqa: E402
    AttributeFlattenFilter,
    RedactionFilter,
    SamplingFilter,
)


class _OtelPipeline:
    """A self-contained in-memory OTel logging pipeline for one logger."""

    def __init__(self, logger_name: str) -> None:
        self._provider = LoggerProvider()
        self._exporter = _InMemoryExporter()  # type: ignore[no-untyped-call]
        self._provider.add_log_record_processor(SimpleLogRecordProcessor(self._exporter))
        self.handler = LoggingHandler(logger_provider=self._provider)
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.addHandler(self.handler)

    def user_attributes(self) -> dict[str, Any]:
        """Return exported attributes from the single record, minus SDK ``code.*``."""
        records = self._exporter.get_finished_logs()
        assert len(records) == 1
        attrs = dict(records[0].log_record.attributes or {})
        return {k: v for k, v in attrs.items() if not k.startswith("code.")}

    def emitted_count(self) -> int:
        return len(self._exporter.get_finished_logs())

    def close(self) -> None:
        self.logger.removeHandler(self.handler)
        self._provider.shutdown()


@pytest.fixture
def otel_pipeline(request: pytest.FixtureRequest) -> Iterator[_OtelPipeline]:
    pipeline = _OtelPipeline(f"afl.otel.filters.{request.node.name}")
    try:
        yield pipeline
    finally:
        pipeline.close()


def test_extra_fields_become_otel_attributes(otel_pipeline: _OtelPipeline) -> None:
    """Baseline: without a filter, ``extra`` leaks straight into OTel attributes."""
    otel_pipeline.logger.info("hello", extra={"password": "s3cret", "safe": "ok"})

    attrs = otel_pipeline.user_attributes()
    assert attrs["password"] == "s3cret"  # unfiltered PII reaches the exporter
    assert attrs["safe"] == "ok"


def test_redaction_filter_masks_pii_through_otel_handler(
    otel_pipeline: _OtelPipeline,
) -> None:
    """A ``RedactionFilter`` on the OTel handler masks PII before export."""
    otel_pipeline.handler.addFilter(RedactionFilter())

    otel_pipeline.logger.info("hello", extra={"password": "s3cret", "safe": "ok"})

    attrs = otel_pipeline.user_attributes()
    assert attrs["password"] == "***"
    assert attrs["safe"] == "ok"


def test_flatten_filter_prevents_nested_dict_drop_through_otel_handler(
    otel_pipeline: _OtelPipeline,
) -> None:
    """An ``AttributeFlattenFilter`` on the OTel handler emits dotted scalar keys."""
    otel_pipeline.handler.addFilter(AttributeFlattenFilter())

    otel_pipeline.logger.info("hello", extra={"order": {"id": 1, "total": 99}})

    attrs = otel_pipeline.user_attributes()
    assert attrs["order.id"] == 1
    assert attrs["order.total"] == 99
    assert "order" not in attrs


def test_redaction_and_flatten_compose_through_otel_handler(
    otel_pipeline: _OtelPipeline,
) -> None:
    """Redaction then flattening compose: nested PII is masked and flattened."""
    otel_pipeline.handler.addFilter(RedactionFilter())
    otel_pipeline.handler.addFilter(AttributeFlattenFilter())

    otel_pipeline.logger.info("hello", extra={"order": {"id": 1, "password": "s3cret"}})

    attrs = otel_pipeline.user_attributes()
    assert attrs["order.id"] == 1
    assert attrs["order.password"] == "***"


def test_sampling_filter_drops_records_through_otel_handler(
    otel_pipeline: _OtelPipeline,
) -> None:
    """A ``SamplingFilter`` on the OTel handler drops records beyond the rate cap."""
    otel_pipeline.handler.addFilter(SamplingFilter(rate=1, window=60.0))

    otel_pipeline.logger.info("first")
    otel_pipeline.logger.info("second")  # exceeds rate=1 within the window

    assert otel_pipeline.emitted_count() == 1


def test_otel_logging_handler_is_import_free_detectable(
    otel_pipeline: _OtelPipeline,
) -> None:
    """The handler is detectable via ``__module__`` without importing OTel (#256)."""
    assert type(otel_pipeline.handler).__module__.startswith("opentelemetry.")
