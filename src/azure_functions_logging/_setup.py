"""Logging setup and environment detection."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
import warnings

from ._context import ContextFilter, install_context_factory
from ._formatter import ColorFormatter
from ._host_config import warn_host_json_level_conflict
from ._json_formatter import JsonFormatter

# Track configured logger names to ensure per-logger idempotency (local mode).
_configured_loggers: set[str | None] = set()
_configured_lock = threading.Lock()

# Azure mode: track which handler ids have been configured and whether the
# root-level ContextFilter has been installed for a given call signature.
# Maps logger_name -> (ContextFilter | None, set[handler_id])
# The ContextFilter is reused across calls to preserve identity and avoid
# adding duplicate filter objects to root.filters.
_azure_state: dict[str | None, tuple[ContextFilter | None, set[int]]] = {}

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
    use_record_factory: bool = False,
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
        use_record_factory: When True, install :func:`install_context_factory`
            so context fields are injected at LogRecord creation time and are
            preserved through queued, delayed, or cross-thread handling. When
            this option is enabled, ``ContextFilter`` is **not** attached to
            handlers, because the global ``LogRecordFactory`` would be
            overwritten by the filter at handler dispatch time. Defaults to
            False to preserve the existing handler-filter-only behavior.

    .. warning::

        ``use_record_factory=True`` modifies the **global**
        ``logging.LogRecordFactory``, which affects all loggers in the process
        (including third-party libraries). The four context field names
        (``invocation_id``, ``function_name``, ``trace_id``, ``cold_start``)
        become reserved LogRecord attributes — passing them via ``extra=`` to
        stdlib loggers will raise ``KeyError``. Prefer :class:`FunctionLogger`
        (which sanitizes ``extra`` keys automatically) when this option is on.
    """
    if format not in {"color", "json"}:
        msg = "format must be 'color' or 'json'"
        raise ValueError(msg)

    # Install the global LogRecordFactory only after argument validation,
    # so an invalid call does not leave persistent global side effects.
    if use_record_factory:
        install_context_factory()

    with _configured_lock:
        is_functions_env = _is_functions_environment()

        if is_functions_env:
            # Azure or Core Tools: install filter on handlers, don't touch level.
            #
            # Recovery semantics: if the host attaches new handlers after the
            # first call, subsequent calls will pick them up. We track which
            # handler ids have already been configured so we don't add duplicate
            # filters/formatters, and reuse the same ContextFilter instance so
            # that root.addFilter() is idempotent (identity-based check).
            if format != "color" and functions_formatter is None:
                warnings.warn(
                    "The 'format' parameter is ignored in Azure Functions environment. "
                    "Pass functions_formatter=JsonFormatter() to set JSON output on host handlers.",
                    stacklevel=2,
                )

            # Retrieve or create the per-call-signature state.
            if logger_name not in _azure_state:
                ctx_filter: ContextFilter | None = (
                    None if use_record_factory else ContextFilter()
                )
                _azure_state[logger_name] = (ctx_filter, set())
            context_filter, configured_handler_ids = _azure_state[logger_name]

            root = logging.getLogger()
            for handler in root.handlers:
                h_id = id(handler)
                if h_id in configured_handler_ids:
                    continue  # already configured — skip to avoid duplicates
                if functions_formatter is not None:
                    handler.setFormatter(functions_formatter)
                if context_filter is not None:
                    handler.addFilter(context_filter)
                configured_handler_ids.add(h_id)

            # Install filter on root logger itself so handlers attached later
            # (before the next setup_logging() call) also inherit it.
            if context_filter is not None and context_filter not in root.filters:
                root.addFilter(context_filter)

            warn_host_json_level_conflict(level, host_json_path=host_json_path)

        else:
            # Standalone local development: full idempotency via logger name.
            if logger_name in _configured_loggers:
                return

            # When the LogRecordFactory is active, attaching ContextFilter would
            # overwrite factory-injected fields at handler dispatch time.
            context_filter = None if use_record_factory else ContextFilter()
            target = logging.getLogger(logger_name)
            target.setLevel(level)

            # Add colored handler only if no handlers exist
            if not target.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(ColorFormatter() if format == "color" else JsonFormatter())
                if context_filter is not None:
                    handler.addFilter(context_filter)
                target.addHandler(handler)
            elif context_filter is not None:
                # Add filter to existing handlers
                for handler in target.handlers:
                    handler.addFilter(context_filter)

            _configured_loggers.add(logger_name)
