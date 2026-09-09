"""Centralized sensitive-key definitions and masking helpers.

Single source of truth for redaction so ``RedactionFilter`` (recursive,
LogRecord-mutating) and ``ColorFormatter`` (inline extra-field masking) share
the same key set and matching rules instead of maintaining separate copies.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

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


# ---------------------------------------------------------------------------
# Value / pattern-based redaction (opt-in)
# ---------------------------------------------------------------------------
#
# Key-based redaction only masks values whose *key* is sensitive. It cannot see
# a secret embedded in a free-text message (``"connecting with token=ghp_x"``).
# ``mask_patterns`` closes that gap by masking substrings that match a secret
# pattern. It is opt-in (off by default) because pattern scanning has a hot-path
# cost and can produce false positives; callers enable it explicitly by passing
# ``patterns=`` to :class:`RedactionFilter`.

# High-confidence secret patterns. Each mask replaces the matched secret with
# ``MASK``. Patterns that define a ``keep`` named group preserve that captured
# prefix (e.g. ``token=``) so the log stays readable while the value is masked.
DEFAULT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # key=value / key: value secrets — keep the key, mask the value.
    re.compile(
        r"(?P<keep>(?i:password|passwd|pwd|token|secret|api[_-]?key|"
        r"access[_-]?key|client[_-]?secret|refresh[_-]?token|authorization)"
        r"\s*[=:]\s*)[^\s,;'\"]+"
    ),
    # Bearer / auth scheme tokens.
    re.compile(r"(?P<keep>(?i:bearer)\s+)[A-Za-z0-9._~+/\-]+=*"),
    # Azure connection-string secrets (AccountKey=, SharedAccessKey=,
    # SharedAccessSignature=, sig=).
    re.compile(
        r"(?P<keep>(?i:AccountKey|SharedAccessKey|SharedAccessSignature|sig)=)"
        r"[^\s;&,'\"]+"
    ),
    # AWS access key id.
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # GitHub personal/OAuth/app/refresh/server tokens.
    re.compile(r"gh[posru]_[A-Za-z0-9]{20,}"),
    # JSON Web Tokens (three base64url segments).
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
)


def _mask_replacement(match: re.Match[str], mask: str) -> str:
    """Return the replacement for one match: ``<keep-prefix>MASK`` or ``MASK``."""
    prefix = match.groupdict().get("keep")
    return f"{prefix}{mask}" if prefix else mask


def mask_patterns(
    text: str,
    patterns: Iterable[re.Pattern[str]] = DEFAULT_PATTERNS,
    mask: str = MASK,
) -> str:
    """Mask substrings of ``text`` that match any secret ``patterns``.

    Each matched span is replaced with ``mask``. When a pattern defines a
    ``keep`` named group, that captured prefix (e.g. ``token=``) is preserved so
    the surrounding message stays readable and only the secret is masked.

    Never raises: a pattern that errors during substitution is skipped so one
    broken rule cannot suppress the others (Principle 3 — redaction failures are
    silent). Non-string / empty input is returned unchanged.
    """
    if not text:
        return text
    result = text
    for pattern in patterns:
        try:
            result = pattern.sub(lambda m: _mask_replacement(m, mask), result)
        except Exception:  # nosec B110 — a broken pattern must not stop others
            continue
    return result
