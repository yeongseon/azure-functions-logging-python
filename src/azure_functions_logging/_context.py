"""Invocation context propagation via contextvars."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import contextvars
import logging
import threading
from typing import Any, NamedTuple
import warnings

# Type alias for the token mapping returned by inject_context()
ContextTokens = dict[contextvars.ContextVar[Any], contextvars.Token[Any]]

# Context variables for invocation context
invocation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "invocation_id", default=None
)
function_name_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "function_name", default=None
)
trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
span_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("span_id", default=None)
cold_start_var: contextvars.ContextVar[bool | None] = contextvars.ContextVar(
    "cold_start", default=None
)

# Cold start detection — lock ensures exactly one concurrent first invocation
# sees cold_start=True even when multiple threads call inject_context() simultaneously.
_cold_start: bool = True
_cold_start_lock = threading.Lock()


def _check_cold_start() -> bool:
    """Check and consume the cold start flag atomically. Returns True only on first call."""
    global _cold_start
    with _cold_start_lock:
        if _cold_start:
            _cold_start = False
            return True
    return False


class ContextFilter(logging.Filter):
    """Logging filter that copies contextvars values onto LogRecord attributes.

    For most new applications, prefer :func:`install_context_factory` because it
    injects context at LogRecord creation time and does not depend on handler
    filter configuration.

    ``ContextFilter`` remains supported for compatibility and for users who do
    not want to modify the global ``LogRecordFactory``.

    This filter is intended to be installed on handlers, so it applies to any
    record that reaches those handlers, including records from third-party
    loggers that propagate to them. For guaranteed record-creation-time
    injection, prefer :func:`install_context_factory`.
    """

    CONTEXT_FIELDS: tuple[str, ...] = (
        "invocation_id",
        "function_name",
        "trace_id",
        "span_id",
        "cold_start",
    )

    def __init__(
        self,
        extra_context_vars: dict[str, contextvars.ContextVar[Any]] | None = None,
    ) -> None:
        """Create the filter, optionally injecting *extra_context_vars*.

        Args:
            extra_context_vars: Optional mapping of ``field_name -> ContextVar``.
                Each variable's current value is copied onto the LogRecord under
                ``field_name`` in addition to the four built-in context fields.
                Field names must not collide with the built-in context fields.
        """
        super().__init__()
        extra = extra_context_vars or {}
        collisions = set(extra) & set(self.CONTEXT_FIELDS)
        if collisions:
            msg = (
                "extra_context_vars field names collide with built-in "
                f"context fields: {', '.join(sorted(collisions))}"
            )
            raise ValueError(msg)
        self._extra_context_vars = dict(extra)

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to the log record. Always returns True."""
        record.invocation_id = invocation_id_var.get()
        record.function_name = function_name_var.get()
        record.trace_id = trace_id_var.get()
        record.span_id = span_id_var.get()
        record.cold_start = cold_start_var.get()
        for field_name, var in self._extra_context_vars.items():
            setattr(record, field_name, var.get())
        return True


_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(ch in _HEX_CHARS for ch in value)


class TraceContextParts(NamedTuple):
    """Parsed components of a W3C ``traceparent`` header.

    All fields preserve the original header casing (hex may be upper or
    lower case per the W3C spec).
    """

    trace_id: str
    span_id: str
    trace_flags: str


def _extract_trace_context(trace_parent: str | None) -> TraceContextParts | None:
    """Parse a ``traceparent`` header into its trace-id, span-id, and flags.

    Applies the same structural validation as :func:`_extract_trace_id`
    (see that function for the full ruleset). Returns a
    :class:`TraceContextParts` when the header is well-formed, otherwise
    ``None`` so callers never propagate garbage identifiers.
    """
    if not trace_parent:
        return None
    try:
        parts = trace_parent.split("-")
        if len(parts) < 4:
            return None
        version, trace_id, parent_id, flags = parts[0], parts[1], parts[2], parts[3]
        if not _is_hex(version, 2) or version.lower() == "ff":
            return None
        # Version 00 must have exactly 4 fields; later versions may extend.
        if version == "00" and len(parts) != 4:
            return None
        if not _is_hex(trace_id, 32) or trace_id == "0" * 32:
            return None
        if not _is_hex(parent_id, 16) or parent_id == "0" * 16:
            return None
        if not _is_hex(flags, 2):
            return None
        return TraceContextParts(trace_id=trace_id, span_id=parent_id, trace_flags=flags)
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        return None

def _extract_trace_id(trace_parent: str | None) -> str | None:
    """Extract a W3C trace-id from a ``traceparent`` header.

    Format (W3C Trace Context Level 1):
        ``<version>-<trace-id>-<parent-id>-<flags>``

    Returns the trace-id only when the header is structurally valid;
    see :func:`_extract_trace_context` for the full validation ruleset.

    Otherwise returns ``None`` so callers never log garbage trace IDs.
    """
    parts = _extract_trace_context(trace_parent)
    return parts.trace_id if parts is not None else None


def inject_context(context: Any) -> ContextTokens:
    """Set invocation context from an Azure Functions context object.

    Extracts invocation_id, function_name, trace_id, and cold_start
    from the provided context and stores them in contextvars.

    This function is safe to call with any object. Missing or inaccessible
    attributes are silently ignored (Principle 3: context injection failures
    never cause application failures).

    Args:
        context: An Azure Functions context object (func.Context).

    Returns:
        A mapping of ContextVar to Token that can be passed to
        ``restore_context()`` to restore the previous state.
    """
    tokens: ContextTokens = {}
    try:
        tokens[invocation_id_var] = invocation_id_var.set(getattr(context, "invocation_id", None))
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        tokens[invocation_id_var] = invocation_id_var.set(None)

    try:
        tokens[function_name_var] = function_name_var.set(getattr(context, "function_name", None))
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        tokens[function_name_var] = function_name_var.set(None)

    try:
        trace_context = getattr(context, "trace_context", None)
        trace_parent = getattr(trace_context, "trace_parent", None) if trace_context else None
        parts = _extract_trace_context(trace_parent)
        tokens[trace_id_var] = trace_id_var.set(parts.trace_id if parts is not None else None)
        tokens[span_id_var] = span_id_var.set(parts.span_id if parts is not None else None)
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        tokens[trace_id_var] = trace_id_var.set(None)
        tokens[span_id_var] = span_id_var.set(None)

    try:
        tokens[cold_start_var] = cold_start_var.set(_check_cold_start())
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        pass
    return tokens


def reset_context() -> None:
    """Clear every invocation context variable.

    Use this for test teardown or defensive full cleanup. For normal
    context management, prefer token-based restore::

        tokens = inject_context(context)
        try:
            ...
        finally:
            restore_context(tokens)

    because token-based restore preserves any outer context.

    Safe to call repeatedly. Setting to ``None`` is the documented \"absent\"
    state for every context field (matches ``ContextVar`` defaults).
    """
    invocation_id_var.set(None)
    function_name_var.set(None)
    trace_id_var.set(None)
    span_id_var.set(None)
    cold_start_var.set(None)


def restore_context(tokens: ContextTokens) -> None:
    """Restore context variables to their previous state using tokens.

    Tokens are single-use and must be restored in the same context where
    they were created. Calling this function twice with the same tokens
    raises ``RuntimeError`` from ``contextvars``.

    Args:
        tokens: Mapping returned by ``inject_context()``.
    """
    for var, token in tokens.items():
        var.reset(token)


# Process-wide default for OpenTelemetry trace-context activation. Toggled by
# ``setup_logging(activate_trace_context=...)`` and consulted by
# ``logging_context`` / ``with_context`` when their per-call flag is ``None``.
_default_trace_context_activation: bool = False


def set_default_trace_context_activation(enabled: bool) -> None:
    """Set the process-wide default for OTel trace-context activation.

    Called by :func:`setup_logging`. When enabled, ``logging_context`` and
    ``with_context`` activate the host trace context unless a per-call
    ``activate_trace_context`` argument overrides it.
    """
    global _default_trace_context_activation
    _default_trace_context_activation = bool(enabled)


def get_default_trace_context_activation() -> bool:
    """Return the current process-wide OTel trace-context activation default."""
    return _default_trace_context_activation


def _read_trace_headers(context: Any) -> tuple[str | None, str | None]:
    """Extract ``(traceparent, tracestate)`` from a context object, never raising."""
    try:
        trace_context = getattr(context, "trace_context", None)
        if trace_context is None:
            return None, None
        trace_parent = getattr(trace_context, "trace_parent", None)
        trace_state = getattr(trace_context, "trace_state", None)
        return trace_parent, trace_state
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        return None, None


@contextmanager
def logging_context(
    context: Any, *, activate_trace_context: bool | None = None
) -> Iterator[None]:
    """Context manager wrapping ``inject_context`` + ``restore_context``.

    Recommended pattern when handlers don't use the ``with_context`` decorator::

        def handler(req, context):
            with logging_context(context):
                logger.info("processing")
                ...

    Guarantees context is restored to its previous state even if the body raises,
    supporting safe nesting of contexts.

    Args:
        context: An Azure Functions context object (func.Context).
        activate_trace_context: When ``True``, also attach the host's W3C trace
            context (from ``context.trace_context``) via OpenTelemetry so log
            records emitted through an OTel ``LoggingHandler`` inherit the host
            span's ``trace_id``/``span_id``. Requires the ``[otel]`` extra;
            degrades to a silent no-op when OpenTelemetry is unavailable. When
            ``None`` (default), the process-wide default configured via
            ``setup_logging(activate_trace_context=...)`` is used.
    """
    should_activate = (
        _default_trace_context_activation
        if activate_trace_context is None
        else activate_trace_context
    )
    tokens = inject_context(context)
    try:
        if should_activate:
            trace_parent, trace_state = _read_trace_headers(context)
            from ._otel import activated_trace_context

            with activated_trace_context(trace_parent, trace_state):
                yield
        else:
            yield
    finally:
        restore_context(tokens)


# --- LogRecordFactory-based context injection (opt-in) ---

_CONTEXT_FACTORY_MARKER = "_azure_functions_logging_context_factory"
_CONTEXT_FACTORY_PREVIOUS = "_azure_functions_logging_previous_factory"

#: Field names injected by the factory. These become reserved LogRecord
#: attributes when ``install_context_factory()`` is active.
CONTEXT_RECORD_FIELDS: tuple[str, ...] = (
    "invocation_id",
    "function_name",
    "trace_id",
    "span_id",
    "cold_start",
)


def _install_context_factory() -> None:
    """Install a global LogRecordFactory that injects context into every LogRecord.

    This is an alternative to ``ContextFilter`` that guarantees context fields
    are present on ALL log records regardless of handler/filter configuration.

    .. warning::

        When this factory is active, the field names ``invocation_id``,
        ``function_name``, ``trace_id``, and ``cold_start`` become **reserved**
        LogRecord attributes. Passing them via ``extra=`` to stdlib loggers will
        raise ``KeyError``. Use :class:`FunctionLogger` (which sanitizes extra
        keys automatically) or choose different key names.

    .. warning::

        This modifies the **global** ``logging.LogRecordFactory``. It affects
        all loggers in the process, including third-party libraries. Call once
        at application startup.

    The factory chains with any previously-installed factory, preserving
    existing customizations.

    This function is idempotent for repeated direct calls while the currently
    active ``LogRecordFactory`` is the context factory installed by this package.
    """
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, _CONTEXT_FACTORY_MARKER, False):
        return

    previous_factory = current_factory

    def context_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        record.invocation_id = invocation_id_var.get()
        record.function_name = function_name_var.get()
        record.trace_id = trace_id_var.get()
        record.span_id = span_id_var.get()
        record.cold_start = cold_start_var.get()
        return record

    setattr(context_record_factory, _CONTEXT_FACTORY_MARKER, True)
    setattr(context_record_factory, _CONTEXT_FACTORY_PREVIOUS, previous_factory)
    logging.setLogRecordFactory(context_record_factory)


def install_context_factory() -> None:
    """Deprecated shim for the LogRecordFactory injection strategy.

    .. deprecated::
        Direct use of ``install_context_factory`` is deprecated in favour of
        the single ``setup_logging(use_record_factory=True)`` entry point,
        which selects the ``LogRecordFactory`` injection strategy and manages
        ``ContextFilter`` teardown consistently. This shim will be removed in
        a future release.
    """
    warnings.warn(
        "install_context_factory() is deprecated; use "
        "setup_logging(use_record_factory=True) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    _install_context_factory()


def uninstall_context_factory() -> bool:
    """Restore the ``LogRecordFactory`` that preceded :func:`install_context_factory`.

    This is the inverse of :func:`install_context_factory` and is primarily
    intended for test teardown, where leaving a global factory installed would
    leak context injection into unrelated tests.

    Only the factory installed by this package is removed: the previously
    active factory (captured at install time, including any chained
    customizations) is restored as the global ``LogRecordFactory``.

    Returns:
        ``True`` if this package's context factory was active and has been
        uninstalled; ``False`` if no such factory was active (no-op).
    """
    current_factory = logging.getLogRecordFactory()
    if not getattr(current_factory, _CONTEXT_FACTORY_MARKER, False):
        return False

    previous_factory = getattr(current_factory, _CONTEXT_FACTORY_PREVIOUS, None)
    if previous_factory is None:  # pragma: no cover - defensive; always set on install
        previous_factory = logging.LogRecord
    logging.setLogRecordFactory(previous_factory)
    return True
