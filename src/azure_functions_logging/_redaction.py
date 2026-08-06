"""Centralized sensitive-key definitions and masking helpers.

Single source of truth for redaction so ``RedactionFilter`` (recursive,
LogRecord-mutating) and ``ColorFormatter`` (inline extra-field masking) share
the same key set and matching rules instead of maintaining separate copies.
"""

from __future__ import annotations

from typing import Any

MASK = "***"

# Default set of sensitive keys masked across the library.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "auth",
        "secret",
        "client_secret",
        "secret_key",
        "api_key",
        "apikey",
        "subscription_key",
        "connection_string",
        "conn_str",
        "sas_token",
        "x_functions_key",
        "function_key",
        "master_key",
        "private_key",
        "credential",
        "account_key",
        "access_key",
    }
)


def normalize_key(key: str) -> str:
    """Normalize a key for sensitive-key lookup: lowercase, hyphens to underscores.

    This ensures HTTP header forms like ``X-Functions-Key`` match the
    underscore-based entries in the sensitive keys set.
    """
    return key.lower().replace("-", "_")


def is_sensitive(key: str, sensitive_keys: frozenset[str] = SENSITIVE_KEYS) -> bool:
    """Return True if ``key`` (after normalization) is a sensitive key.

    Matches when either:

    - the full normalized key is in ``sensitive_keys``, or
    - **any** dotted segment of the normalized key is in ``sensitive_keys``.

    The dotted-segment check is a safety net for keys produced by
    :class:`~azure_functions_logging._filters.AttributeFlattenFilter`, which
    rewrites ``{"order": {"password": "x"}}`` into the scalar key
    ``order.password`` and ``{"token": {"raw": "x"}}`` into ``token.raw``.
    Without matching *any* segment, a flatten-before-redact ordering would ship
    nested secrets unmasked whenever the sensitive name is a parent and the leaf
    is benign (e.g. ``token.raw``, ``secret.value``, ``credential.blob``).
    Segment matching is against ``.``-delimited whole segments, not substrings,
    so non-sensitive keys like ``partition.key``, ``metrics.token_count``, and
    ``tokenizer.name`` are left untouched. A benign leaf under a sensitive parent
    (e.g. ``password.hint``) is fail-closed masked, which is the correct posture
    for a security control.
    """
    normalized = normalize_key(key)
    if normalized in sensitive_keys:
        return True
    return any(seg in sensitive_keys for seg in normalized.split("."))


def mask_value(
    key: str,
    value: Any,
    sensitive_keys: frozenset[str] = SENSITIVE_KEYS,
    mask: str = MASK,
) -> Any:
    """Return ``mask`` if ``key`` is sensitive, otherwise the original ``value``."""
    return mask if is_sensitive(key, sensitive_keys) else value
