"""Tests for the optional OpenTelemetry trace-context activation (issue #255).

These validate the production ``activated_trace_context`` context manager that
attaches the host's W3C trace context so an OTel ``LoggingHandler`` stamps
emitted records with the host span's ``trace_id``/``span_id`` — without this
package ever creating, recording, or exporting a span.

The OTel-dependent tests skip cleanly when ``opentelemetry-api`` is absent, so
the base install stays zero-dependency.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from azure_functions_logging import _otel

_TRACE_ID_HEX = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_ID_HEX = "00f067aa0ba902b7"
_TRACEPARENT = f"00-{_TRACE_ID_HEX}-{_PARENT_ID_HEX}-01"


@pytest.fixture(autouse=True)
def _reset_otel_availability_cache() -> Iterator[None]:
    # ``is_available`` caches its result process-wide; reset around every test
    # so import-monkeypatching stays isolated and order-independent.
    _otel._reset_availability()
    yield
    _otel._reset_availability()


def test_is_available_reflects_otel_import() -> None:
    # In this repo's test env opentelemetry-api is installed, so this is True.
    pytest.importorskip("opentelemetry.context")
    assert _otel.is_available() is True


def test_activated_trace_context_is_noop_when_traceparent_missing() -> None:
    # Must not raise and must yield even with no traceparent.
    with _otel.activated_trace_context(None):
        pass
    with _otel.activated_trace_context(""):
        pass


def test_activated_trace_context_noop_when_otel_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_otel, "is_available", lambda: False)
    # Even with a valid traceparent, absence of OTel must degrade to a no-op.
    with _otel.activated_trace_context(_TRACEPARENT):
        pass


def test_activated_trace_context_binds_host_span() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    assert not trace.get_current_span().get_span_context().is_valid
    with _otel.activated_trace_context(_TRACEPARENT):
        span_context = trace.get_current_span().get_span_context()
        assert span_context.is_valid
        assert span_context.is_remote is True
        assert format(span_context.trace_id, "032x") == _TRACE_ID_HEX
        assert format(span_context.span_id, "016x") == _PARENT_ID_HEX
    # Context restored (LIFO detach) after the block.
    assert not trace.get_current_span().get_span_context().is_valid


def test_activated_trace_context_detaches_on_exception() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    with pytest.raises(ValueError):
        with _otel.activated_trace_context(_TRACEPARENT):
            raise ValueError("boom")
    assert not trace.get_current_span().get_span_context().is_valid


def test_activated_trace_context_honours_trace_state() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    with _otel.activated_trace_context(_TRACEPARENT, trace_state="vendor=abc"):
        span_context = trace.get_current_span().get_span_context()
        assert span_context.is_valid
        assert span_context.trace_state.get("vendor") == "abc"


def test_activated_trace_context_survives_malformed_traceparent() -> None:
    # A structurally invalid traceparent must never raise out of the CM.
    with _otel.activated_trace_context("not-a-valid-traceparent"):
        pass


# ---------------------------------------------------------------------------
# Integration: activation wired through the public entry points
# ---------------------------------------------------------------------------


def _make_context(
    trace_parent: str | None = _TRACEPARENT,
    trace_state: str | None = None,
) -> SimpleNamespace:

    return SimpleNamespace(
        invocation_id="inv-1",
        function_name="fn-a",
        trace_context=SimpleNamespace(
            trace_parent=trace_parent,
            trace_state=trace_state,
        ),
    )


def test_logging_context_activates_host_span_when_enabled() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    from azure_functions_logging import logging_context

    with logging_context(_make_context(), activate_trace_context=True):
        sc = trace.get_current_span().get_span_context()
        assert sc.is_valid
        assert format(sc.span_id, "016x") == _PARENT_ID_HEX
    assert not trace.get_current_span().get_span_context().is_valid


def test_logging_context_does_not_activate_when_explicitly_disabled() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    from azure_functions_logging import logging_context
    from azure_functions_logging._context import set_default_trace_context_activation

    # An explicit per-call ``False`` must override the auto default and stay off,
    # even when OpenTelemetry is importable.
    try:
        set_default_trace_context_activation(None)
        with logging_context(_make_context(), activate_trace_context=False):
            assert not trace.get_current_span().get_span_context().is_valid
    finally:
        set_default_trace_context_activation(None)


def test_logging_context_auto_activates_when_otel_available() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    from azure_functions_logging import logging_context
    from azure_functions_logging._context import set_default_trace_context_activation

    # Auto tier (#255): with no explicit flag and no configured default,
    # activation is enabled iff opentelemetry-api is importable — which it is
    # in this test env.
    try:
        set_default_trace_context_activation(None)
        with logging_context(_make_context()):
            assert trace.get_current_span().get_span_context().is_valid
    finally:
        set_default_trace_context_activation(None)


def test_with_context_activates_host_span_when_enabled() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    from azure_functions_logging import with_context

    seen: dict[str, bool] = {}

    @with_context(activate_trace_context=True)
    def handler(req: object, context: object) -> str:
        seen["valid"] = trace.get_current_span().get_span_context().is_valid
        return "ok"

    assert handler(None, _make_context()) == "ok"
    assert seen["valid"] is True
    assert not trace.get_current_span().get_span_context().is_valid


def test_setup_logging_sets_default_activation() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    from azure_functions_logging import logging_context, setup_logging
    from azure_functions_logging._context import set_default_trace_context_activation

    try:
        setup_logging(logger_name="afl.otel.default", activate_trace_context=True)
        with logging_context(_make_context()):
            assert trace.get_current_span().get_span_context().is_valid
    finally:
        set_default_trace_context_activation(None)


def test_setup_logging_bare_call_preserves_explicit_activation() -> None:
    """A later argument-less ``setup_logging()`` must not revert a previously
    configured activation default (idempotency — reviewer finding)."""
    from azure_functions_logging import setup_logging
    from azure_functions_logging._context import (
        get_default_trace_context_activation,
        set_default_trace_context_activation,
    )

    try:
        setup_logging(logger_name="afl.otel.idempotent", activate_trace_context=True)
        # A bare call (activate_trace_context defaults to None) must leave the
        # explicitly-set default intact rather than silently reverting to auto.
        setup_logging(logger_name="afl.otel.idempotent.b")
        assert get_default_trace_context_activation() is True
    finally:
        set_default_trace_context_activation(None)


# ---------------------------------------------------------------------------
# Auto tier (#255): default None resolves to "enabled iff opentelemetry-api
# is importable".
# ---------------------------------------------------------------------------


def test_get_default_activation_auto_enabled_when_otel_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from azure_functions_logging import _context

    monkeypatch.setattr(_context, "_default_trace_context_activation", None)
    monkeypatch.setattr(_otel, "is_available", lambda: True)
    assert _context.get_default_trace_context_activation() is True


def test_get_default_activation_auto_disabled_when_otel_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from azure_functions_logging import _context

    monkeypatch.setattr(_context, "_default_trace_context_activation", None)
    monkeypatch.setattr(_otel, "is_available", lambda: False)
    assert _context.get_default_trace_context_activation() is False


def test_get_default_activation_explicit_overrides_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from azure_functions_logging import _context

    # An explicit stored default short-circuits the auto probe entirely.
    monkeypatch.setattr(_context, "_default_trace_context_activation", False)
    monkeypatch.setattr(_otel, "is_available", lambda: True)
    assert _context.get_default_trace_context_activation() is False


def test_resolve_auto_returns_false_when_otel_import_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    from azure_functions_logging import _context

    # Simulate the base (zero-dependency) install where importing the helper's
    # ``is_available`` path is fine but OTel itself is absent.
    monkeypatch.setitem(sys.modules, "opentelemetry.context", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.propagate", None)
    assert _context._resolve_auto_trace_context_activation() is False


# ---------------------------------------------------------------------------
# _otel silent-failure paths (Principle 3): every branch degrades to a no-op.
# ---------------------------------------------------------------------------


def test_is_available_false_when_import_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "opentelemetry.context", None)
    assert _otel.is_available() is False


def test_is_available_caches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    # First call with the import broken caches ``False``.
    monkeypatch.setitem(sys.modules, "opentelemetry.context", None)
    assert _otel.is_available() is False
    # Restoring the import must NOT change the cached result until reset.
    monkeypatch.undo()
    assert _otel.is_available() is False
    # Explicit reset re-evaluates importability.
    _otel._reset_availability()
    pytest.importorskip("opentelemetry.context")
    assert _otel.is_available() is True


def test_activated_trace_context_noop_when_extract_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    pytest.importorskip("opentelemetry.context")
    # OTel appears available (is_available forced True), but importing the
    # propagate API inside the context manager fails.
    monkeypatch.setattr(_otel, "is_available", lambda: True)
    monkeypatch.setitem(sys.modules, "opentelemetry.propagate", None)
    with _otel.activated_trace_context(_TRACEPARENT):
        pass


def test_activated_trace_context_noop_when_attach_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import context as otel_context

    def _boom(_ctx: object) -> None:
        raise RuntimeError("attach failed")

    monkeypatch.setattr(otel_context, "attach", _boom)
    # Attach failure must be swallowed; the block still runs and detach is skipped.
    with _otel.activated_trace_context(_TRACEPARENT):
        pass


def test_activated_trace_context_swallows_detach_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import context as otel_context

    real_detach = otel_context.detach

    def _boom(token: object) -> None:
        # Perform the real detach first so global OTel context is not leaked
        # into later tests, then raise to exercise the silent-cleanup branch.
        real_detach(token)  # type: ignore[arg-type]
        raise RuntimeError("detach failed")

    monkeypatch.setattr(otel_context, "detach", _boom)
    # A failing detach on cleanup must never propagate.
    with _otel.activated_trace_context(_TRACEPARENT):
        pass


# ---------------------------------------------------------------------------
# End-to-end correlation: a real OTel LoggingHandler must stamp records emitted
# inside ``activated_trace_context`` with the host span's trace_id/span_id.
# ---------------------------------------------------------------------------


def test_otel_logging_handler_stamps_host_trace_ids() -> None:
    pytest.importorskip("opentelemetry.sdk._logs")
    import logging

    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import (
        InMemoryLogExporter,
        SimpleLogRecordProcessor,
    )

    exporter = InMemoryLogExporter()  # type: ignore[no-untyped-call]
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)

    logger = logging.getLogger("afl.otel.correlation")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    try:
        with _otel.activated_trace_context(_TRACEPARENT):
            logger.info("correlated")
    finally:
        logger.removeHandler(handler)
        provider.shutdown()

    emitted = exporter.get_finished_logs()
    assert len(emitted) == 1
    record = emitted[0].log_record
    # The handler inherits the host's remote span context (issue #282).
    assert format(record.trace_id, "032x") == _TRACE_ID_HEX
    assert format(record.span_id, "016x") == _PARENT_ID_HEX


def test_otel_logging_handler_has_no_trace_ids_outside_activation() -> None:
    pytest.importorskip("opentelemetry.sdk._logs")
    import logging

    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import (
        InMemoryLogExporter,
        SimpleLogRecordProcessor,
    )

    exporter = InMemoryLogExporter()  # type: ignore[no-untyped-call]
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)

    logger = logging.getLogger("afl.otel.correlation.none")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.info("uncorrelated")
    finally:
        logger.removeHandler(handler)
        provider.shutdown()

    emitted = exporter.get_finished_logs()
    assert len(emitted) == 1
    # No active host span -> invalid (zero) ids, proving activation is the source.
    assert emitted[0].log_record.trace_id in (0, None)
