"""Canonical worker-compatibility metadata helpers.

This module houses the primitive shared across the Azure Functions Python DX
Toolkit for copying identity attributes from a user handler onto a decorator
wrapper **without** tripping the Azure Functions worker's function-indexing
heuristics.

The primitive is intentionally kept as a small, dependency-free unit so the
**same shape** can be mirrored verbatim across sibling packages
(``azure-functions-logging``, ``azure-functions-validation``, ...). These
packages are independent PyPI distributions with no shared base dependency, so
"shared" here means a canonical, synced definition rather than a common import.

Ref: https://github.com/yeongseon/azure-functions-logging/issues/216
"""

from __future__ import annotations

from typing import Any, Callable

# Identity attributes copied from the wrapped function onto the wrapper.
#
# ``functools.wraps`` / ``functools.update_wrapper`` are deliberately NOT used:
#
# * they set ``__wrapped__ = func`` — the Azure Functions worker may follow it
#   during function indexing and bind the original (un-wrapped) handler instead
#   of the wrapper, defeating the decorator;
# * they copy ``__dict__`` — sharing the dict object aliases
#   ``wrapper.__dict__`` with ``func.__dict__``, so later ``setattr`` calls
#   (e.g. ``_azure_functions_metadata``) leak onto the original ``func``.
SAFE_IDENTITY_ATTRS: tuple[str, ...] = (
    "__name__",
    "__qualname__",
    "__doc__",
    "__module__",
)


def copy_identity_attrs(
    wrapper: Callable[..., Any],
    func: Callable[..., Any],
    attrs: tuple[str, ...] = SAFE_IDENTITY_ATTRS,
) -> None:
    """Copy safe identity attributes from ``func`` onto ``wrapper`` in place.

    Copies only the attributes in ``attrs`` (identity metadata) and neither
    sets ``__wrapped__`` nor copies ``__dict__``. Signature and annotation
    handling is intentionally left to the caller because it is
    package-specific (some packages hide parameters, others preserve them).
    """
    for attr in attrs:
        try:
            object.__setattr__(wrapper, attr, getattr(func, attr))
        except (AttributeError, TypeError):  # pragma: no cover
            pass
