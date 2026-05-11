"""Invocation context propagation via contextvars."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import contextvars
import logging
from typing import Any

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
cold_start_var: contextvars.ContextVar[bool | None] = contextvars.ContextVar(
    "cold_start", default=None
)

# Cold start detection
_cold_start: bool = True


def _check_cold_start() -> bool:
    """Check and consume the cold start flag. Returns True only on first call."""
    global _cold_start
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
        "cold_start",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to the log record. Always returns True."""
        record.invocation_id = invocation_id_var.get()
        record.function_name = function_name_var.get()
        record.trace_id = trace_id_var.get()
        record.cold_start = cold_start_var.get()
        return True


_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(ch in _HEX_CHARS for ch in value)


def _extract_trace_id(trace_parent: str | None) -> str | None:
    """Extract a W3C trace-id from a ``traceparent`` header.

    Format (W3C Trace Context Level 1):
        ``<version>-<trace-id>-<parent-id>-<flags>``

    Returns the trace-id only when the header is structurally valid:
      * exactly 4 ``-``-separated parts,
      * version: 2 hex chars (``ff`` is reserved — rejected),
      * trace-id: 32 hex chars and not all-zero,
      * parent/span-id: 16 hex chars and not all-zero,
      * flags: 2 hex chars,
      * version ``00`` enforces the strict 4-part shape; future versions are
        accepted as long as the first 4 fields parse — trailing fields are
        ignored to stay forward-compatible with later spec revisions.

    Otherwise returns ``None`` so callers never log garbage trace IDs.
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
        return trace_id
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
        tokens[trace_id_var] = trace_id_var.set(_extract_trace_id(trace_parent))
    except Exception:  # nosec B110 — Principle 3: context failures are silent
        tokens[trace_id_var] = trace_id_var.set(None)

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


@contextmanager
def logging_context(context: Any) -> Iterator[None]:
    """Context manager wrapping ``inject_context`` + ``restore_context``.

    Recommended pattern when handlers don't use the ``with_context`` decorator::

        def handler(req, context):
            with logging_context(context):
                logger.info("processing")
                ...

    Guarantees context is restored to its previous state even if the body raises,
    supporting safe nesting of contexts.
    """
    tokens = inject_context(context)
    try:
        yield
    finally:
        restore_context(tokens)


# --- LogRecordFactory-based context injection (opt-in) ---

_CONTEXT_FACTORY_MARKER = "_azure_functions_logging_context_factory"

#: Field names injected by the factory. These become reserved LogRecord
#: attributes when ``install_context_factory()`` is active.
CONTEXT_RECORD_FIELDS: tuple[str, ...] = (
    "invocation_id",
    "function_name",
    "trace_id",
    "cold_start",
)


def install_context_factory() -> None:
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
        record.cold_start = cold_start_var.get()
        return record

    setattr(context_record_factory, _CONTEXT_FACTORY_MARKER, True)
    logging.setLogRecordFactory(context_record_factory)
