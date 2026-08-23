"""Invocation context propagation via contextvars."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import contextvars
import functools
import logging
import threading
from typing import Any, NamedTuple, ParamSpec, TypeVar

from ._constants import _CONTEXT_FIELD_NAMES
from ._host_instance import get_host_instance_id

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


def _validate_extra_context_vars(
    extra_context_vars: dict[str, contextvars.ContextVar[Any]] | None,
) -> dict[str, contextvars.ContextVar[Any]]:
    """Validate and copy user *extra_context_vars*, rejecting built-in collisions.

    Shared by :class:`ContextFilter` and :func:`_install_context_factory` so both
    context-injection strategies enforce the identical collision rule: a
    user-supplied field name must not shadow one of the built-in context fields
    (:data:`_CONTEXT_FIELD_NAMES`).

    Returns a shallow copy of the mapping so later caller mutations do not affect
    the stored variables.

    Raises:
        ValueError: If any field name collides with a built-in context field.
    """
    extra = extra_context_vars or {}
    collisions = set(extra) & set(_CONTEXT_FIELD_NAMES)
    if collisions:
        msg = (
            "extra_context_vars field names collide with built-in "
            f"context fields: {', '.join(sorted(collisions))}"
        )
        raise ValueError(msg)
    return dict(extra)


class ContextFilter(logging.Filter):
    """Logging filter that copies contextvars values onto LogRecord attributes.

    ``ContextFilter`` is the default context-injection strategy: it is
    installed on handlers (and the root logger) by ``setup_logging()`` unless
    ``use_record_factory=True`` is passed. Because it runs at handler dispatch
    time, it applies to any record that reaches those handlers, including
    records from third-party loggers that propagate to them.

    The opt-in alternative, ``setup_logging(use_record_factory=True)``, injects
    context at LogRecord creation time and does not depend on handler/filter
    wiring, but it mutates the **global** ``logging.LogRecordFactory`` (affecting
    every logger in the process) and turns the context field names into reserved
    LogRecord attributes. Choose it when you need guaranteed record-creation-time
    injection and accept those global side effects; otherwise this filter is the
    safe default.
    """

    #: Canonical context field names, aliased from the single source of truth in
    #: ``_constants`` so the injection order never drifts between modules.
    CONTEXT_FIELDS: tuple[str, ...] = _CONTEXT_FIELD_NAMES

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
        self._extra_context_vars = _validate_extra_context_vars(extra_context_vars)

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to the log record. Always returns True."""
        record.invocation_id = invocation_id_var.get()
        record.function_name = function_name_var.get()
        record.trace_id = trace_id_var.get()
        record.span_id = span_id_var.get()
        record.cold_start = cold_start_var.get()
        record.host_instance_id = get_host_instance_id()
        for field_name, var in self._extra_context_vars.items():
            setattr(record, field_name, var.get())
        return True


_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(ch in _HEX_CHARS for ch in value)


class TraceContextParts(NamedTuple):
    """Parsed components of a W3C ``traceparent`` header.

    ``trace_id`` and ``span_id`` are normalized to lowercase hex so they match
    OpenTelemetry's W3C-canonical (lowercase-only) identifiers. ``trace_flags``
    is the parsed integer value of the 2-hex-digit trace-flags field.
    """

    trace_id: str
    span_id: str
    trace_flags: int | None


def _extract_trace_context(trace_parent: str | None) -> TraceContextParts | None:
    """Parse a ``traceparent`` header into its trace-id, span-id, and flags.

    Performs full W3C Trace Context Level 1 structural validation:
    a 2-hex ``version`` (excluding ``ff``), a 32-hex ``trace-id`` and
    16-hex ``parent-id`` (both rejected when all-zero), and 2-hex
    ``flags``. Returns a :class:`TraceContextParts` when the header is
    well-formed, otherwise ``None`` so callers never propagate garbage
    identifiers.
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
        return TraceContextParts(
            trace_id=trace_id.lower(), span_id=parent_id.lower(), trace_flags=int(flags, 16)
        )
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        return None


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


# --- Background-thread context propagation ---

_P = ParamSpec("_P")
_R = TypeVar("_R")

#: Invocation context variables propagated by :func:`propagate_context`.
_PROPAGATED_CONTEXT_VARS: tuple[contextvars.ContextVar[Any], ...] = (
    invocation_id_var,
    function_name_var,
    trace_id_var,
    span_id_var,
    cold_start_var,
)

_MISSING = object()


def propagate_context(
    func: Callable[_P, _R],
    *,
    context: Any = None,
) -> Callable[_P, _R]:
    """Bind the current invocation context to *func* for background-thread execution.

    Invocation context is stored in :mod:`contextvars`, which do **not** propagate
    to :class:`~concurrent.futures.ThreadPoolExecutor` workers or manually created
    :class:`threading.Thread` targets. Wrapping a callable with
    ``propagate_context`` snapshots the current invocation context fields
    (``invocation_id``, ``function_name``, ``trace_id``, ``span_id``,
    ``cold_start``) **at wrap time** and re-applies them inside the wrapper when
    it later runs on another thread, then restores the previous values on exit so
    pooled threads never leak context between tasks.

    Wrap the callable inside the invocation whose context should be propagated,
    immediately before handing work to a thread or executor::

        from concurrent.futures import ThreadPoolExecutor

        def handler(req, context):
            with logging_context(context):
                with ThreadPoolExecutor() as pool:
                    pool.submit(propagate_context(do_work, context=context), payload)

    When an Azure Functions ``context`` object is supplied, the worker's
    ``thread_local_storage.invocation_id`` is also set for the duration of the
    call (and restored afterwards) so the worker's own logging handler correlates
    records emitted from the background thread. This is best-effort and
    duck-typed: any missing attribute or error is silently ignored (Principle 3:
    context propagation failures never crash the caller). No ``azure-functions``
    import is required.

    Args:
        func: The callable to run on a background thread. Called with whatever
            positional/keyword arguments the returned wrapper receives.
        context: Optional Azure Functions context object (``func.Context``). When
            provided, its ``invocation_id`` is propagated to the worker's
            ``thread_local_storage`` in addition to the ``contextvars`` snapshot.

    Returns:
        A wrapper around *func* that applies the snapshotted context on entry and
        restores the previous state on exit. Reusable and concurrency-safe: it may
        be submitted to multiple threads simultaneously.
    """
    snapshot: tuple[tuple[contextvars.ContextVar[Any], Any], ...] = tuple(
        (var, var.get()) for var in _PROPAGATED_CONTEXT_VARS
    )

    inv_id: Any = None
    tls: Any = None
    if context is not None:
        try:
            inv_id = getattr(context, "invocation_id", None)
            tls = getattr(context, "thread_local_storage", None)
        except Exception:  # nosec B110 — Principle 3: context failures are silent
            inv_id = None
            tls = None

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        tokens: list[tuple[contextvars.ContextVar[Any], contextvars.Token[Any]]] = []
        previous_tls_invocation_id: Any = _MISSING
        tls_was_set = False
        try:
            for var, value in snapshot:
                tokens.append((var, var.set(value)))
            if tls is not None and inv_id is not None:
                try:
                    previous_tls_invocation_id = getattr(tls, "invocation_id", _MISSING)
                    tls.invocation_id = inv_id
                    tls_was_set = True
                except Exception:  # nosec B110 — Principle 3: context failures are silent
                    tls_was_set = False
            return func(*args, **kwargs)
        finally:
            if tls_was_set:
                try:
                    if previous_tls_invocation_id is _MISSING:
                        try:
                            del tls.invocation_id
                        except Exception:  # nosec B110 — Principle 3: silent
                            tls.invocation_id = None
                    else:
                        tls.invocation_id = previous_tls_invocation_id
                except Exception:  # nosec B110 — Principle 3: context failures are silent
                    pass
            for var, token in reversed(tokens):
                var.reset(token)

    return wrapper


# Process-wide default for OpenTelemetry trace-context activation. Toggled by
# ``setup_logging(activate_trace_context=...)`` and consulted by
# ``logging_context`` / ``with_context`` when their per-call flag is ``None``.
# Trace-context activation is strictly opt-in: the default is ``False`` so the
# library never attaches the host trace context unless explicitly asked to.
_default_trace_context_activation: bool = False


def set_default_trace_context_activation(enabled: bool) -> None:
    """Set the process-wide default for OTel trace-context activation.

    Called by :func:`setup_logging`. When enabled, ``logging_context`` and
    ``with_context`` activate the host trace context unless a per-call
    ``activate_trace_context`` argument overrides it. Activation is opt-in;
    the default is ``False`` until a caller explicitly enables it.
    """
    global _default_trace_context_activation
    _default_trace_context_activation = bool(enabled)


def get_default_trace_context_activation() -> bool:
    """Return the process-wide OTel trace-context activation default.

    Defaults to ``False`` (opt-in); toggled via
    ``setup_logging(activate_trace_context=...)``.
    """
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
def logging_context(context: Any, *, activate_trace_context: bool | None = None) -> Iterator[None]:
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
            ``None`` (default), the process-wide default configured via
            ``setup_logging(activate_trace_context=...)`` is used, which itself
            defaults to ``False`` (activation is strictly opt-in).
    """
    should_activate = (
        get_default_trace_context_activation()
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


def _install_context_factory(
    extra_context_vars: dict[str, contextvars.ContextVar[Any]] | None = None,
) -> None:
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

    Args:
        extra_context_vars: Optional mapping of ``field_name -> ContextVar``
            whose current values are copied onto every record alongside the
            built-in context fields, mirroring :class:`ContextFilter`. Field
            names must not collide with the built-in context fields.

    Raises:
        ValueError: If any *extra_context_vars* field name collides with a
            built-in context field. Validation runs before any global state is
            mutated, so an invalid call installs nothing.
    """
    extra = _validate_extra_context_vars(extra_context_vars)
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
        record.host_instance_id = get_host_instance_id()
        for field_name, var in extra.items():
            setattr(record, field_name, var.get())
        return record

    setattr(context_record_factory, _CONTEXT_FACTORY_MARKER, True)
    setattr(context_record_factory, _CONTEXT_FACTORY_PREVIOUS, previous_factory)
    logging.setLogRecordFactory(context_record_factory)


def _uninstall_context_factory() -> bool:
    """Restore the ``LogRecordFactory`` that preceded :func:`_install_context_factory`.

    This is the inverse of :func:`_install_context_factory` and is primarily
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
