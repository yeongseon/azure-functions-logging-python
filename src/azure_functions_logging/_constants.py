"""Centralized reserved/excluded LogRecord key sets.

Single source of truth for the reserved-key frozensets shared across
``_logger``, ``_formatter``, and ``_filters``. Keeping them here prevents the
sets from drifting independently between modules.
"""

from __future__ import annotations

import logging

# Custom keys this library injects via the logger context (factory). Defined once
# here as an ordered tuple (the canonical injection order used by ``ContextFilter``
# and the LogRecordFactory) and derived into a frozenset below. They must be
# treated as reserved alongside stdlib LogRecord attributes so that user-supplied
# `extra` does not silently overwrite Azure Functions runtime metadata.
#
# Single source of truth: ``_context.ContextFilter.CONTEXT_FIELDS`` aliases this
# tuple, so the field-name list never drifts between modules.
_CONTEXT_FIELD_NAMES: tuple[str, ...] = (
    "invocation_id",
    "function_name",
    "trace_id",
    "span_id",
    "cold_start",
    "host_instance_id",
)

_LIBRARY_RESERVED_KEYS: frozenset[str] = frozenset(_CONTEXT_FIELD_NAMES)

# `message` and `asctime` are computed lazily by formatters and absent from
# `__dict__`; we add them explicitly to preserve the original guarantee.
#
# `taskName` is also kept in the explicit forward-compat set so that user code
# passing it as `extra` is sanitized identically across 3.10 / 3.11 / 3.12+.
_FORWARD_COMPAT_RECORD_KEYS: frozenset[str] = frozenset({"message", "asctime", "taskName"})

# stdlib LogRecord fields only (no library context keys).
# Derive the stdlib LogRecord attribute set at import time from a pristine record
# created directly via the base class, bypassing the global LogRecordFactory.
# Using logging.makeLogRecord({}) would pick up any custom factory already
# installed by third-party libraries, misclassifying their injected fields as
# reserved stdlib attributes and breaking extra-key sanitization and redaction.
_STDLIB_RECORD_KEYS: frozenset[str] = (
    frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | _FORWARD_COMPAT_RECORD_KEYS
)

_RESERVED_LOG_RECORD_KEYS: frozenset[str] = _STDLIB_RECORD_KEYS | _LIBRARY_RESERVED_KEYS
