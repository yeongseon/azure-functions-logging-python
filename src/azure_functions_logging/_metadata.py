"""Typed cross-package metadata contract for the ``logging`` namespace.

Toolkit convention (shared across the Azure Functions Python DX Toolkit):
decorators attach an ``_azure_functions_metadata`` dict onto the wrapped
handler, keyed by a package-owned *namespace* string, so sibling packages can
discover metadata **without importing this package**.

This module gives the ``"logging"`` namespace payload a checked ``TypedDict``
shape plus a single merge helper. The contract is intentionally *replicated*
across toolkit packages (not shared via a runtime dependency); keep the
``_BaseMetadata`` ``version`` field and the merge-without-clobber semantics
identical to the sibling packages.

Ref: https://github.com/yeongseon/azure-functions-logging-python/issues/216
"""

from __future__ import annotations

from typing import Any, TypedDict, cast

#: Convention attribute name shared across all toolkit packages.
METADATA_ATTR = "_azure_functions_metadata"

#: Namespace owned by this package.
NAMESPACE = "logging"

#: Schema version for the ``logging`` namespace payload.
LOGGING_METADATA_VERSION = 1


class _BaseMetadata(TypedDict):
    """Fields common to every toolkit namespace payload."""

    version: int


class LoggingMetadata(_BaseMetadata):
    """Shape of ``_azure_functions_metadata["logging"]`` (schema version 1)."""

    context_param: str


def set_logging_metadata(
    wrapper: Any,
    func: Any,
    payload: LoggingMetadata,
) -> None:
    """Merge the ``logging`` namespace onto ``wrapper`` without clobbering others.

    Seeds from any pre-existing convention attribute on ``func`` (set by other
    decorators applied before this one), merges in ``payload`` under the
    ``logging`` namespace, and writes the result onto ``wrapper`` only. The
    original ``func`` is left untouched so the metadata never leaks onto
    undecorated references.
    """
    existing = getattr(func, METADATA_ATTR, None)
    base: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    base[NAMESPACE] = payload
    setattr(wrapper, METADATA_ATTR, base)


def read_logging_metadata(func: Any) -> LoggingMetadata | None:
    """Return the typed ``logging`` namespace payload, or ``None`` if absent."""
    md = getattr(func, METADATA_ATTR, None)
    if isinstance(md, dict):
        entry = md.get(NAMESPACE)
        if isinstance(entry, dict):
            return cast("LoggingMetadata", entry)
    return None
