"""azure-functions-logging — Developer-friendly logging for Azure Functions Python."""

from __future__ import annotations

from ._context import (
    ContextTokens,
    inject_context,
    install_context_factory,
    logging_context,
    reset_context,
    restore_context,
)
from ._decorator import get_logging_metadata, with_context
from ._filters import RedactionFilter, SamplingFilter
from ._json_formatter import JsonFormatter
from ._logger import FunctionLogger
from ._setup import setup_logging

__all__ = [
    "__version__",
    "ContextTokens",
    "FunctionLogger",
    "JsonFormatter",
    "RedactionFilter",
    "SamplingFilter",
    "get_logging_metadata",
    "get_logger",
    "inject_context",
    "install_context_factory",
    "logging_context",
    "reset_context",
    "restore_context",
    "setup_logging",
    "with_context",
]

__version__ = "0.7.7"


def get_logger(name: str | None = None) -> FunctionLogger:
    """Create a ``FunctionLogger`` wrapping a standard ``logging.Logger``.

    Args:
        name: Logger name. Typically ``__name__``.

    Returns:
        A ``FunctionLogger`` instance.
    """
    import logging

    return FunctionLogger(logging.getLogger(name))
