"""Secure profile ownership and handler installation (no implicit instrumentation)."""

import logging
import re
import threading

from ._context import _register_entry_hook
from ._filters import RedactionFilter
from ._isolated_handler import IsolatedHandler
from ._redaction import DEFAULT_PATTERNS, SENSITIVE_KEYS

# Proxy credentials, Azure shared-access credentials and ingestion configuration
# are credential-bearing fields missing from the compatibility-frozen defaults.
_SECURE_KEYS = SENSITIVE_KEYS | frozenset(
    {
        "proxy_authorization",
        "shared_access_key",
        "shared_access_signature",
        "instrumentation_key",
        "instrumentationkey",
        "applicationinsights_connection_string",
        "azure_monitor_connection_string",
        "azure_web_jobs_storage",
        "azurewebjobsstorage",
    }
)
_lock = threading.RLock()
# Process-lifetime secure-profile state: set by configure_secure_redaction() and
# consulted at every invocation entry. Ordinary setup_logging() never clears it.
_secure_enabled = False
_SECURE_PATTERNS = (
    re.compile(r"(?P<keep>(?i:authorization)\s*[=:]\s*(?i:basic)\s+)[^\s,;'\"]+"),
    re.compile(
        r"(?P<keep>(?<![\w])['\"]?(?i:password|passwd|pwd|token|secret|"
        r"api[_-]?key|access[_-]?token|client[_-]?secret|connection[_-]?string)"
        r"['\"]?\s*[=:]\s*)"
        r"(?:'[^']*'|\"[^\"]*\")"
    ),
    *DEFAULT_PATTERNS,
)


class _SecureRedactionFilter(RedactionFilter):
    def __init__(self) -> None:
        super().__init__(sensitive_keys=_SECURE_KEYS, patterns=_SECURE_PATTERNS, fail_closed=True)


def attach_secure_redaction(handler: logging.Handler) -> None:
    """Protect a handler before registering it, after its enrichment filters.

    Idempotently installs the secure profile as the last filter, before any
    formatter/exporter. Call again after adding other mutating filters. For an
    IsolatedHandler, also protects the target after target-local enrichment.
    Does not change levels, formatters, handler ownership, or context injection.

    This is the explicit contract for handlers registered *during* an active
    invocation: the automatic entry-time reconciliation only covers handlers that
    exist when the next ``logging_context`` / ``with_context`` entry runs.
    """
    with _lock:
        owned = next((f for f in handler.filters if type(f) is _SecureRedactionFilter), None)
        if owned is None or handler.filters[-1] is not owned:
            handler.filters = [
                f for f in handler.filters if type(f) is not _SecureRedactionFilter
            ] + [owned if owned is not None else _SecureRedactionFilter()]
        if isinstance(handler, IsolatedHandler):
            attach_secure_redaction(handler.target)


def _all_handlers() -> set[logging.Handler]:
    """Handlers on the root logger and every named logger (propagating or not)."""
    while True:
        try:
            loggers = (logging.getLogger(), *tuple(logging.Logger.manager.loggerDict.values()))
            return {
                h for lg in loggers if isinstance(lg, logging.Logger) for h in tuple(lg.handlers)
            }
        except RuntimeError:  # loggerDict mutated by another thread while copying
            continue


def configure_secure_redaction(*, enabled: bool = True) -> None:
    """Apply the secure preset to current handlers after logging/exporter setup.

    Includes named loggers and isolated targets. Enabling is retained for the
    process lifetime: each ``logging_context`` / ``with_context`` entry re-protects
    handlers registered since (root, named, non-propagating and isolated targets),
    keeping the secure filter last. A handler added *during* an invocation, or an
    unsupported logging graph, is covered from the next entry or via
    ``attach_secure_redaction``; this is not an unconditional fail-closed guarantee.
    Disabling removes only exact package-owned secure filters and stops
    reconciliation; ordinary setup does not disable it.
    Never changes handler ownership, levels, formatters, or context strategy.
    """
    global _secure_enabled
    with _lock:
        _secure_enabled = enabled
        handlers = _all_handlers()
        while handlers:
            handler = handlers.pop()
            if enabled:
                attach_secure_redaction(handler)
            else:
                handler.filters = [
                    f for f in handler.filters if type(f) is not _SecureRedactionFilter
                ]
                if isinstance(handler, IsolatedHandler):
                    handlers.add(handler.target)


def _reconcile_secure_handlers() -> None:
    """Re-protect handlers registered since the last scan while secure mode is on."""
    if not _secure_enabled:
        return
    with _lock:
        if not _secure_enabled:
            return
        for handler in _all_handlers():
            attach_secure_redaction(handler)


_register_entry_hook(20, _reconcile_secure_handlers)
