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
    """Return True if ``key`` (after normalization) is a sensitive key."""
    return normalize_key(key) in sensitive_keys


def mask_value(
    key: str,
    value: Any,
    sensitive_keys: frozenset[str] = SENSITIVE_KEYS,
    mask: str = MASK,
) -> Any:
    """Return ``mask`` if ``key`` is sensitive, otherwise the original ``value``."""
    return mask if is_sensitive(key, sensitive_keys) else value
