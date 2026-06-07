"""Optional log filters for azure-functions-logging.

Provides:
- ``SamplingFilter``: Rate-limit noisy loggers to reduce gRPC/stdout pressure.
- ``RedactionFilter``: Mask PII / sensitive keys on LogRecord extra fields.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Iterable

from ._logger import _RESERVED_LOG_RECORD_KEYS

# Default set of sensitive keys masked by RedactionFilter
_DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "connection_string",
    }
)

_MASK = "***"


_REDACT_MAX_DEPTH = 10  # default depth limit for recursive redaction


def _redact_value(
    value: Any,
    sensitive_keys: frozenset[str],
    mask: str = _MASK,
    *,
    _seen: set[int] | None = None,
    _depth: int = 0,
) -> Any:
    """Recursively redact sensitive keys from dicts/lists.

    Guarded against:
    - Cyclic references (via id-based seen set)
    - Pathologically deep structures (via _depth / _REDACT_MAX_DEPTH);
      over-limit values are masked (fail-closed) to prevent leaking sensitive
      data buried in unexpectedly deep payloads
    - All exceptions (returns value unmodified on any error)
    """
    try:
        if _depth >= _REDACT_MAX_DEPTH:
            return mask  # treat over-deep structures as potentially sensitive
        if isinstance(value, dict):
            seen = _seen if _seen is not None else set()
            obj_id = id(value)
            if obj_id in seen:
                return mask  # cyclic reference detected
            seen = seen | {obj_id}  # copy to avoid cross-branch pollution
            return {
                key: (
                    mask
                    if isinstance(key, str) and key.lower() in sensitive_keys
                    else _redact_value(
                        item, sensitive_keys, mask, _seen=seen, _depth=_depth + 1
                    )
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            seen = _seen if _seen is not None else set()
            obj_id = id(value)
            if obj_id in seen:
                return mask
            seen = seen | {obj_id}
            return [
                _redact_value(item, sensitive_keys, mask, _seen=seen, _depth=_depth + 1)
                for item in value
            ]
        return value
    except Exception:  # nosec B110 — filter must never raise
        return value




class SamplingFilter(logging.Filter):
    """Rate-limit a logger to emit at most ``rate`` records per ``window`` seconds.

    Useful for high-frequency loggers (e.g. per-request HTTP logs, polling
    loops) that can saturate the Azure Functions gRPC channel.

    All records that exceed the rate cap are silently dropped. Records at
    WARNING and above are **always** passed through, regardless of the cap.

    Args:
        rate: Maximum number of records to pass per window. Must be >= 1.
        window: Rolling time window in seconds. Default: 1.0.
        name: Optional logger-name scope. When set, only matching loggers are
            subject to sampling; non-matching records pass through unchanged.
            Empty string matches all loggers (default).

    Example::

        filter = SamplingFilter(rate=10, window=1.0)
        handler.addFilter(filter)
    """

    def __init__(self, rate: int = 100, window: float = 1.0, name: str = "") -> None:
        super().__init__(name)
        if rate < 1:
            msg = "rate must be >= 1"
            raise ValueError(msg)
        if window <= 0:
            msg = "window must be > 0"
            raise ValueError(msg)
        self._rate = rate
        self._window = window
        self._lock = threading.Lock()
        self._count: int = 0
        self._window_start: float = time.monotonic()

    def filter(self, record: logging.LogRecord) -> bool:
        """Return True to emit the record, False to drop it."""
        # Honor name-based scoping from logging.Filter
        if not super().filter(record):
            return True  # bypass sampling for non-matching loggers

        # Always pass WARNING and above
        if record.levelno >= logging.WARNING:
            return True

        now = time.monotonic()
        with self._lock:
            if now - self._window_start >= self._window:
                self._count = 0
                self._window_start = now
            self._count += 1
            return self._count <= self._rate


class RedactionFilter(logging.Filter):
    """Mask PII / sensitive values on LogRecord extra attributes in-place.

    Iterates over all non-standard attributes on the ``LogRecord`` and
    replaces the value of any key whose *lowercased* name is in
    ``sensitive_keys`` with ``"***"``.

    This filter mutates the record in-place so both ``ColorFormatter`` and
    ``JsonFormatter`` see redacted values.

    Args:
        sensitive_keys: Iterable of lowercase key names to redact. When None,
            uses the built-in default set:
            ``password``, ``passwd``, ``token``, ``access_token``,
            ``refresh_token``, ``authorization``, ``secret``,
            ``client_secret``, ``api_key``, ``apikey``, ``connection_string``.
        name: Optional logger-name scope. When set, only matching loggers are
            subject to redaction; non-matching records pass through unchanged.
    Example::

        filter = RedactionFilter()
        handler.addFilter(filter)
    """

    def __init__(
        self,
        sensitive_keys: Iterable[str] | None = None,
        name: str = "",
    ) -> None:
        super().__init__(name)
        self._sensitive_keys: frozenset[str] = (
            frozenset(k.lower() for k in sensitive_keys)
            if sensitive_keys is not None
            else _DEFAULT_SENSITIVE_KEYS
        )

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive fields on the record. Always returns True."""
        # Honor name-based scoping from logging.Filter
        if not super().filter(record):
            return True  # bypass redaction for non-matching loggers

        try:
            for key in list(record.__dict__.keys()):
                try:
                    if key in _RESERVED_LOG_RECORD_KEYS:
                        continue
                    if key.lower() in self._sensitive_keys:
                        setattr(record, key, _MASK)
                    else:
                        value = record.__dict__[key]
                        if isinstance(value, (dict, list)):
                            setattr(record, key, _redact_value(value, self._sensitive_keys))
                except Exception:  # nosec B110 — one broken field must not stop others
                    pass
        except Exception:  # nosec B110 — filter must never raise
            pass
        return True
