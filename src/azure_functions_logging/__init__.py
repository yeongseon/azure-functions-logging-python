"""azure-functions-logging — Developer-friendly logging for Azure Functions Python."""

from __future__ import annotations

from ._context import (
    ContextTokens,
    PropagatingExecutor,
    inject_context,
    logging_context,
    propagate_context,
    propagating_executor,
    reset_context,
    restore_context,
)
from ._decorator import get_logging_metadata, with_context
from ._filters import AttributeFlattenFilter, RedactionFilter, SamplingFilter
from ._json_formatter import JsonFormatter
from ._logger import FunctionLogger
from ._redaction import DEFAULT_PATTERNS as DEFAULT_REDACTION_PATTERNS
from ._setup import setup_logging

__all__ = [
    "__version__",
    "AttributeFlattenFilter",
    "ContextTokens",
    "DEFAULT_REDACTION_PATTERNS",
    "FunctionLogger",
    "get_logger",
    "get_logging_metadata",
    "inject_context",
    "JsonFormatter",
    "logging_context",
    "propagate_context",
    "PropagatingExecutor",
    "propagating_executor",
    "RedactionFilter",
    "reset_context",
    "restore_context",
    "SamplingFilter",
    "setup_logging",
    "with_context",
]

__version__ = "0.12.0"


def get_logger(name: str | None = None) -> FunctionLogger:
    """Create a ``FunctionLogger`` wrapping a standard ``logging.Logger``.

    Args:
        name: Logger name. Typically ``__name__``.

    Returns:
        A ``FunctionLogger`` instance.
    """
    import logging

    return FunctionLogger(logging.getLogger(name))
