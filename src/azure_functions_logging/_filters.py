"""Optional log filters for azure-functions-logging.

Provides:
- ``SamplingFilter``: Rate-limit noisy loggers to reduce gRPC/stdout pressure.
- ``RedactionFilter``: Mask PII / sensitive keys on LogRecord extra fields.
- ``AttributeFlattenFilter``: Flatten nested dict extras to dotted scalar keys
  so OpenTelemetry does not silently drop them.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Iterable

from ._constants import _RESERVED_LOG_RECORD_KEYS
from ._redaction import MASK as _MASK
from ._redaction import SENSITIVE_KEYS as _DEFAULT_SENSITIVE_KEYS
from ._redaction import is_sensitive as _is_sensitive
from ._redaction import normalize_key as _normalize_key

_REDACT_MAX_DEPTH = 10  # default depth limit for recursive redaction
_FLATTEN_MAX_DEPTH = 10  # default depth limit for recursive flattening


def _flatten_dict(
    prefix: str,
    value: dict[Any, Any],
    separator: str,
    max_depth: int,
    *,
    _seen: set[int] | None = None,
    _depth: int = 0,
) -> dict[str, Any]:
    """Flatten a nested dict into ``{dotted_key: scalar}`` pairs.

    Guarded against:
    - Cyclic references (via id-based seen set); cyclic sub-dicts are dropped.
    - Pathologically deep structures (via ``_depth`` / ``max_depth``); the
      remaining nested dict at the depth limit is emitted as-is under its
      dotted key.

    Lists (and any non-dict leaf) are emitted unchanged under their dotted key.
    Empty dicts contribute no keys. Non-string keys are skipped (they cannot
    form a queryable dotted path). On key collision — e.g. a nested ``{"a":
    {"b": 1}}`` and a literal ``{"a.b": 2}`` both mapping to ``a.b`` — the
    first value encountered in iteration order wins and later collisions are
    dropped silently (never overwritten).
    """
    if _depth >= max_depth:
        return {prefix: value}
    seen = _seen if _seen is not None else set()
    obj_id = id(value)
    if obj_id in seen:
        return {}  # cyclic reference detected
    seen = seen | {obj_id}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue  # non-string keys cannot form a queryable dotted path
        new_key = f"{prefix}{separator}{key}"
        if isinstance(item, dict):
            for sub_key, sub_item in _flatten_dict(
                new_key, item, separator, max_depth, _seen=seen, _depth=_depth + 1
            ).items():
                if sub_key not in result:  # keep-first-wins on collision
                    result[sub_key] = sub_item
        elif new_key not in result:  # keep-first-wins on collision
            result[new_key] = item
    return result


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
                    if isinstance(key, str) and _is_sensitive(key, sensitive_keys)
                    else _redact_value(item, sensitive_keys, mask, _seen=seen, _depth=_depth + 1)
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
        per_logger: When False (default), all matching records share one rate
            bucket per filter instance. When True, each ``record.name`` has an
            independent bucket/window. Best suited for finite logger-name
            cardinality (e.g. module-based loggers). Stale buckets are
            automatically evicted to prevent unbounded memory growth.

    Example::

        filter = SamplingFilter(rate=10, window=1.0)
        handler.addFilter(filter)
    """

    _MAX_BUCKETS: int = 1024  # evict stale entries when exceeded

    def __init__(
        self,
        rate: int = 100,
        window: float = 1.0,
        name: str = "",
        *,
        per_logger: bool = False,
    ) -> None:
        super().__init__(name)
        if rate < 1:
            msg = "rate must be >= 1"
            raise ValueError(msg)
        if window <= 0:
            msg = "window must be > 0"
            raise ValueError(msg)
        self._rate: int = rate
        self._window: float = window
        self._lock: threading.Lock = threading.Lock()
        self._per_logger: bool = per_logger
        self._count: int = 0
        self._window_start: float = time.monotonic()
        # per_logger state: {record.name: (window_start, count)}
        self._buckets: dict[str, tuple[float, int]] = {}
        self._last_eviction: float = 0.0  # monotonic timestamp of last eviction

    def _evict_stale_buckets(self, now: float) -> None:
        """Remove per-logger buckets whose window has expired, then enforce hard cap.

        First removes stale entries (window expired). If the bucket count still
        exceeds _MAX_BUCKETS, drops the oldest buckets by window_start to enforce
        a deterministic memory bound.

        Called opportunistically when bucket count exceeds _MAX_BUCKETS.
        Must be called while holding self._lock.
        """
        stale_cutoff = now - self._window
        self._buckets = {
            name: entry for name, entry in self._buckets.items() if entry[0] > stale_cutoff
        }
        # Hard cap: if still over limit after stale removal, drop oldest buckets
        if len(self._buckets) > self._MAX_BUCKETS:
            sorted_entries = sorted(self._buckets.items(), key=lambda x: x[1][0])
            self._buckets = dict(sorted_entries[len(sorted_entries) - self._MAX_BUCKETS :])

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
            if self._per_logger:
                bucket = self._buckets.get(record.name)
                if bucket is None or now - bucket[0] >= self._window:
                    self._buckets[record.name] = (now, 1)
                    # Opportunistic eviction when over capacity
                    if len(self._buckets) > self._MAX_BUCKETS:
                        if now - self._last_eviction >= self._window:
                            # Full stale sweep (throttled to once per window)
                            self._evict_stale_buckets(now)
                            self._last_eviction = now
                        elif len(self._buckets) > self._MAX_BUCKETS:
                            # Throttle blocked full sweep; enforce hard cap
                            # by dropping the single oldest bucket
                            oldest_name = min(self._buckets, key=lambda k: self._buckets[k][0])
                            del self._buckets[oldest_name]
                    return True
                count = bucket[1] + 1
                self._buckets[record.name] = (bucket[0], count)
                return count <= self._rate

            if now - self._window_start >= self._window:
                self._count = 0
                self._window_start = now
            self._count += 1
            return self._count <= self._rate


class RedactionFilter(logging.Filter):
    """Mask PII / sensitive values on LogRecord extra attributes in-place.

    Iterates over all non-standard attributes on the ``LogRecord`` and
    replaces the value of any key whose *normalized* name is in
    ``sensitive_keys`` with ``"***"``.

    Key normalization: lowercased, hyphens replaced with underscores.
    This means ``X-Functions-Key`` matches the entry ``x_functions_key``.

    This filter mutates the record in-place so both ``ColorFormatter`` and
    ``JsonFormatter`` see redacted values.

    Args:
        sensitive_keys: Iterable of key names to redact (case-insensitive,
            hyphen-insensitive). When None, uses the built-in default set
            (25 keys):
            ``password``, ``passwd``, ``pwd``, ``token``, ``access_token``,
            ``refresh_token``, ``id_token``, ``authorization``, ``auth``,
            ``secret``, ``client_secret``, ``secret_key``, ``api_key``,
            ``apikey``, ``subscription_key``, ``connection_string``,
            ``conn_str``, ``sas_token``, ``x_functions_key``,
            ``function_key``, ``master_key``, ``private_key``,
            ``credential``, ``account_key``, ``access_key``.
        name: Optional logger-name scope. When set, only matching loggers are
            subject to redaction; non-matching records pass through unchanged.

    Note:
        The default set includes ``credential`` which may over-redact
        in codebases that use generic attribute names. Pass an explicit
        ``sensitive_keys`` set if false positives occur.
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
            frozenset(_normalize_key(k) for k in sensitive_keys)
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
                    if _is_sensitive(key, self._sensitive_keys):
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


class AttributeFlattenFilter(logging.Filter):
    """Flatten nested ``dict`` extras into dotted scalar attributes in-place.

    OpenTelemetry attributes only permit scalars and homogeneous arrays. A
    nested ``dict`` passed via ``extra`` (e.g. ``order={"id": 1}``) is silently
    dropped by the OTel SDK. This filter rewrites such attributes into dotted
    scalar keys (``order.id``) so the data survives export.

    The filter mutates the record in-place, removing the original nested-dict
    attribute and adding one attribute per leaf. It is **opt-in**: it has no
    effect unless explicitly attached to a handler/logger.

    Behavior:
    - Nested dicts are flattened recursively to dotted keys.
    - Lists / heterogeneous arrays are left unchanged (emitted as-is under
      their dotted key). OTel accepts homogeneous scalar arrays; heterogeneous
      or nested-object arrays remain the caller's responsibility.
    - Scalar attributes and reserved ``LogRecord`` keys are never touched.
    - Empty dicts contribute no keys (the attribute is removed).
    - Cyclic references are dropped; over-deep structures (beyond
      ``max_depth``) are emitted as-is at the depth boundary.

    .. note::

        This filter rewrites the record's attributes, so it also affects
        **non-OTel** consumers reading the same record — e.g. a
        :class:`JsonFormatter` on the root handler will emit ``order.id``
        instead of a nested ``order`` object. To avoid changing your JSON log
        shape, attach this filter only to the OpenTelemetry ``LoggingHandler``
        rather than to the root handler.

    Args:
        name: Optional logger-name scope. When set, only matching loggers are
            flattened; non-matching records pass through unchanged.
        separator: Delimiter joining nested keys. Default ``"."``.
        max_depth: Maximum recursion depth before a nested dict is emitted
            as-is. Default ``10``.

    Example::

        filter = AttributeFlattenFilter()
        handler.addFilter(filter)
    """

    def __init__(
        self,
        name: str = "",
        *,
        separator: str = ".",
        max_depth: int = _FLATTEN_MAX_DEPTH,
    ) -> None:
        super().__init__(name)
        self._separator: str = separator
        self._max_depth: int = max_depth

    def filter(self, record: logging.LogRecord) -> bool:
        """Flatten nested-dict fields on the record. Always returns True."""
        # Honor name-based scoping from logging.Filter
        if not super().filter(record):
            return True  # bypass flattening for non-matching loggers

        try:
            for key in list(record.__dict__.keys()):
                try:
                    if key in _RESERVED_LOG_RECORD_KEYS:
                        continue
                    value = record.__dict__[key]
                    if not isinstance(value, dict):
                        continue
                    flattened = _flatten_dict(key, value, self._separator, self._max_depth)
                    del record.__dict__[key]
                    for flat_key, flat_value in flattened.items():
                        setattr(record, flat_key, flat_value)
                except Exception:  # nosec B110 — one broken field must not stop others
                    pass
        except Exception:  # nosec B110 — filter must never raise
            pass
        return True
