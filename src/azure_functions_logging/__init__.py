"""azure-functions-logging — Developer-friendly logging for Azure Functions Python."""

from __future__ import annotations

from ._context import (
    ContextTokens,
    inject_context,
    install_context_factory,
    logging_context,
    reset_context,
    restore_context,
    uninstall_context_factory,
)
from ._decorator import get_logging_metadata, with_context
from ._filters import AttributeFlattenFilter, RedactionFilter, SamplingFilter
from ._json_formatter import JsonFormatter
from ._logger import FunctionLogger
from ._setup import setup_logging

__all__ = [
    "__version__",
    "AttributeFlattenFilter",
    "ContextTokens",
    "FunctionLogger",
    "get_logger",
    "get_logging_metadata",
    "inject_context",
    "install_context_factory",
    "JsonFormatter",
    "logging_context",
    "RedactionFilter",
    "reset_context",
    "restore_context",
    "SamplingFilter",
    "setup_logging",
    "uninstall_context_factory",
    "with_context",
]

__version__ = "0.8.0"


def get_logger(name: str | None = None) -> FunctionLogger:
    """Create a ``FunctionLogger`` wrapping a standard ``logging.Logger``.

    Args:
        name: Logger name. Typically ``__name__``.

    Returns:
        A ``FunctionLogger`` instance.
    """
    import logging

    return FunctionLogger(logging.getLogger(name))
