"""Optional OpenTelemetry trace-context activation for log correlation.

This module lets ``azure-functions-logging`` bind the Azure Functions host's
incoming W3C trace context into the current execution context so that an
OpenTelemetry ``LoggingHandler`` (owned by the host or the user's OTel setup)
stamps emitted log records with the host span's ``trace_id`` and ``span_id``.

Design constraints (see README "What this package does not do"):

* This package never creates, records, or exports a span. It only *attaches*
  the already-existing remote span context extracted from the ``traceparent``
  header, using :func:`opentelemetry.context.attach` /
  :func:`opentelemetry.context.detach`.
* ``opentelemetry-api`` is an **optional** dependency (the ``[otel]`` extra).
  The base install stays zero-dependency: every entry point degrades to a
  silent no-op when OpenTelemetry is not importable.
* Consistent with Principle 3 ("context failures are silent"), no code path
  here raises as a result of trace-context handling.

Known limitation: OpenTelemetry's runtime context is contextvar-based, so
correlation does **not** propagate into worker threads spawned via
``ThreadPoolExecutor`` / ``run_in_executor``. Logs emitted from such threads
are orphaned. This matches the behaviour pinned by the spike test suite.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

_available: bool | None = None


def is_available() -> bool:
    """Return ``True`` when the OpenTelemetry API is importable.

    Only the API package (``opentelemetry-api``) is required — the SDK,
    exporters, and a ``TracerProvider`` are owned by the host or the user.

    The result is cached after the first call: importability does not change
    over a process lifetime, and this runs on the per-log hot path.
    """
    global _available
    if _available is not None:
        return _available
    try:
        import opentelemetry.context
        import opentelemetry.propagate  # noqa: F401
    except Exception:  # nosec B110 — optional dependency; absence is expected
        _available = False
    else:
        _available = True
    return _available


def _reset_availability() -> None:
    """Clear the cached :func:`is_available` result (test-only helper)."""
    global _available
    _available = None


@contextmanager
def activated_trace_context(
    trace_parent: str | None,
    trace_state: str | None = None,
) -> Iterator[None]:
    """Attach the host trace context for the duration of the ``with`` block.

    While the block is active, OpenTelemetry's "current span" is the
    non-recording remote span described by *trace_parent*, so any log record
    emitted through an OTel ``LoggingHandler`` inherits the host's
    ``trace_id`` and ``span_id``.

    The context is always detached (LIFO) on exit, including when the block
    raises, so no trace context leaks into the next invocation on a reused
    worker.

    This is a silent no-op — yielding without attaching anything — when:

    * *trace_parent* is empty/``None``;
    * OpenTelemetry is not installed (:func:`is_available` is ``False``);
    * the extracted span context is invalid (a no-op span) -- attaching it
      would break the trace tree, so the current context is left untouched;
    * a valid **local** span is already active in the current context (e.g. the
      OTel distro's auto-instrumentation or the user's
      ``start_as_current_span``); overwriting it with the host's non-recording
      remote span would strip the real ``span_id`` from log records and
      re-parent nested spans, so the already-active local span is left in
      place -- it already supplies correlation. A currently-active *remote*
      span (i.e. a host traceparent attached by an enclosing activation) is
      NOT protected: a nested activation may replace it with its own host
      context;
    * extraction/attach fails for any reason (malformed header, etc.).

    Args:
        trace_parent: The W3C ``traceparent`` header value from the host.
        trace_state: The optional W3C ``tracestate`` header value.
    """
    if not trace_parent or not is_available():
        yield
        return

    try:
        from opentelemetry import context as otel_context
        from opentelemetry import trace as otel_trace
        from opentelemetry.propagate import extract as otel_extract
    except Exception:  # nosec B110 — optional dependency; degrade to no-op
        yield
        return

    carrier: dict[str, str] = {"traceparent": trace_parent}
    if trace_state:
        carrier["tracestate"] = trace_state

    token = None
    try:
        extracted = otel_extract(carrier)
        # Attach the host's remote span context only when it is BOTH valid AND
        # there is no already-active *real local* span in the current context.
        #
        # An invalid/no-op extracted context (e.g. the host emitted no real
        # trace) must not be attached: downstream records would be parented to
        # an invalid context and the trace tree would break.
        #
        # A currently-active *local* span (worker auto-instrumentation or the
        # user's own ``start_as_current_span``) must win: this helper exists to
        # rescue records orphaned (``span_id=0``) precisely BECAUSE no span is
        # active. Overwriting a real local span with the host's non-recording
        # remote span would break the very log<->span correlation the feature
        # promises and flatten nested spans -- leave it untouched.
        #
        # A currently-active *remote* span is only a previously-attached host
        # traceparent, not a real worker span, so a nested activation is allowed
        # to replace it (see test_spike_nested_contexts_restore_outer_span).
        span_context = otel_trace.get_current_span(extracted).get_span_context()
        current_span_context = otel_trace.get_current_span().get_span_context()
        current_is_real_local_span = (
            current_span_context.is_valid and not current_span_context.is_remote
        )
        if span_context.is_valid and not current_is_real_local_span:
            token = otel_context.attach(extracted)
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        token = None

    try:
        yield
    finally:
        if token is not None:
            try:
                otel_context.detach(token)
            except Exception:  # nosec B110 — Principle 3: silent on cleanup
                pass
