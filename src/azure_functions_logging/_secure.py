"""Secure profile ownership and handler installation (no implicit instrumentation)."""

import logging
import re
import threading

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
    """
    with _lock:
        owned = next((f for f in handler.filters if type(f) is _SecureRedactionFilter), None)
        handler.filters = [f for f in handler.filters if type(f) is not _SecureRedactionFilter] + [
            owned if owned is not None else _SecureRedactionFilter()
        ]
        if isinstance(handler, IsolatedHandler):
            attach_secure_redaction(handler.target)


def configure_secure_redaction(*, enabled: bool = True) -> None:
    """Apply the secure preset to current handlers after logging/exporter setup.

    Includes named loggers and isolated targets. Reapply after registering late
    handlers or use attach_secure_redaction before registration. Disabling removes
    only exact package-owned secure filters; ordinary setup does not disable it.
    Never changes handler ownership, levels, formatters, or context strategy.
    """
    loggers = (logging.getLogger(), *tuple(logging.Logger.manager.loggerDict.values()))
    handlers = {
        h for logger in loggers if isinstance(logger, logging.Logger) for h in logger.handlers
    }
    with _lock:
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
