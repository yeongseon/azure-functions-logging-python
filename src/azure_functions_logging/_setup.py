"""Logging setup and environment detection."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
import warnings

from ._context import ContextFilter
from ._formatter import ColorFormatter
from ._host_config import warn_host_json_level_conflict
from ._json_formatter import JsonFormatter

# Track configured logger names to ensure per-logger idempotency
_configured_loggers: set[str | None] = set()
_configured_lock = threading.Lock()


def _is_functions_environment() -> bool:
    """Check if running inside Azure Functions (hosted or Core Tools)."""
    return bool(os.environ.get("FUNCTIONS_WORKER_RUNTIME"))


def _is_azure_hosted() -> bool:
    """Check if running in Azure-hosted environment (not local Core Tools)."""
    return bool(os.environ.get("WEBSITE_INSTANCE_ID"))


def setup_logging(
    *,
    level: int = logging.INFO,
    format: str = "color",
    logger_name: str | None = None,
    functions_formatter: logging.Formatter | None = None,
    host_json_path: Path | str | None = None,
) -> None:
    """Configure logging for the current environment.
    Behavior depends on the detected environment:

    - **Azure / Core Tools**: Installs ``ContextFilter`` on the root logger's
      handlers only. Does NOT add handlers or modify the root logger level
      (respects ``host.json`` configuration). If ``functions_formatter`` is
      provided, it is applied to every root handler before the filter is added.
    - **Standalone local development**: Adds a ``StreamHandler`` with
      ``ColorFormatter`` or ``JsonFormatter`` to the specified logger
      (or root logger if ``logger_name`` is None). Sets the level.

    This function is idempotent per ``logger_name`` — calling it multiple times
    for the same logger has no additional effect.

    Args:
        level: Logging level for local development. Ignored in Azure/Core Tools.
        format: Log output format for local development. Supported values are
            ``"color"`` (default) and ``"json"``. Ignored when
            ``functions_formatter`` is provided. In Azure/Core Tools, passing
            ``format="json"`` without ``functions_formatter`` emits a warning.
        logger_name: Optional logger name to configure. When None, configures
            the root logger (local dev) or installs filter on root handlers (Azure).
        functions_formatter: Optional custom formatter applied to all root
            handlers when running inside Azure/Core Tools. Useful for
            injecting a custom JSON formatter or third-party formatter
            without losing ContextFilter integration.
        host_json_path: Optional explicit path to a ``host.json`` file used by
            the host-level conflict warning. When ``None`` (default),
            ``host.json`` is auto-discovered by walking up from the current
            working directory (bounded). Pass an explicit path to disable
            auto-discovery in environments where it might pick the wrong file.
    """
    if format not in {"color", "json"}:
        msg = "format must be 'color' or 'json'"
        raise ValueError(msg)

    with _configured_lock:
        if logger_name in _configured_loggers:
            return

        context_filter = ContextFilter()
        is_functions_env = _is_functions_environment()

        if is_functions_env:
            # Azure or Core Tools: install filter only, don't touch handlers/level
            if format != "color" and functions_formatter is None:
                warnings.warn(
                    "The 'format' parameter is ignored in Azure Functions environment. "
                    "Pass functions_formatter=JsonFormatter() to set JSON output on host handlers.",
                    stacklevel=2,
                )
            root = logging.getLogger()
            for handler in root.handlers:
                if functions_formatter is not None:
                    handler.setFormatter(functions_formatter)
                handler.addFilter(context_filter)
            # Also install on any future handlers via the logger itself
            root.addFilter(context_filter)
        else:
            # Standalone local development
            target = logging.getLogger(logger_name)
            target.setLevel(level)

            # Add colored handler only if no handlers exist
            if not target.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(ColorFormatter() if format == "color" else JsonFormatter())
                handler.addFilter(context_filter)
                target.addHandler(handler)
            else:
                # Add filter to existing handlers
                for handler in target.handlers:
                    handler.addFilter(context_filter)

        if is_functions_env:
            warn_host_json_level_conflict(level, host_json_path=host_json_path)

        _configured_loggers.add(logger_name)
