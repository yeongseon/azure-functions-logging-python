"""Tests for the optional OpenTelemetry trace-context activation (issue #255).

These validate the production ``activated_trace_context`` context manager that
attaches the host's W3C trace context so an OTel ``LoggingHandler`` stamps
emitted records with the host span's ``trace_id``/``span_id`` — without this
package ever creating, recording, or exporting a span.

The OTel-dependent tests skip cleanly when ``opentelemetry-api`` is absent, so
the base install stays zero-dependency.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from azure_functions_logging import _otel

_TRACE_ID_HEX = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_ID_HEX = "00f067aa0ba902b7"
_TRACEPARENT = f"00-{_TRACE_ID_HEX}-{_PARENT_ID_HEX}-01"


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


def test_logging_context_does_not_activate_by_default() -> None:
    pytest.importorskip("opentelemetry.context")
    from opentelemetry import trace

    from azure_functions_logging import logging_context

    with logging_context(_make_context()):
        assert not trace.get_current_span().get_span_context().is_valid


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
        set_default_trace_context_activation(False)
