"""Logging setup and environment detection."""

from __future__ import annotations

import contextvars
import logging
import os
from pathlib import Path
import threading
from typing import Any
import warnings
import weakref

from ._context import ContextFilter, _install_context_factory, set_default_trace_context_activation
from ._formatter import ColorFormatter
from ._host_config import warn_host_json_level_conflict, warn_otel_logging_misconfig
from ._json_formatter import JsonFormatter

# Track configured logger names to ensure per-logger idempotency (local mode).
_configured_loggers: set[str | None] = set()
_configured_lock = threading.Lock()

# Azure mode: track which handlers have been configured for a given call
# signature. Keyed by (logger_name, use_record_factory) so that a later call
# with different factory semantics gets its own ContextFilter instance.
# WeakSet is used for handlers so stale references are cleaned up automatically
# when the host replaces a handler — preventing both false 'already configured'
# hits from id reuse and unbounded set growth in long-lived workers.
_AzureStateKey = tuple[str | None, bool]
_AzureStateValue = tuple[ContextFilter | None, "weakref.WeakSet[logging.Handler]"]
_azure_state: dict[_AzureStateKey, _AzureStateValue] = {}


def _remove_context_filters(logger: logging.Logger) -> None:
    """Remove all package-owned ContextFilter instances from *logger* and its handlers.

    Uses ``type(f) is ContextFilter`` so user subclasses with additional behaviour
    are preserved.
    """
    for f in tuple(logger.filters):
        if type(f) is ContextFilter:
            logger.removeFilter(f)
    for handler in logger.handlers:
        for f in tuple(handler.filters):
            if type(f) is ContextFilter:
                handler.removeFilter(f)


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
    extra_context_vars: dict[str, contextvars.ContextVar[Any]] | None = None,
    activate_trace_context: bool | None = None,
) -> None:
    """Configure logging for the current environment.
    Behavior depends on the detected environment:

    - **Azure / Core Tools** (``use_record_factory=False``, default): Installs
      ``ContextFilter`` on the root logger's existing handlers **and** on the
      root logger itself (so handlers attached later also receive context
      fields). Does NOT add new handlers or modify the root logger level
      (respects ``host.json`` configuration). If ``functions_formatter`` is
      provided, it is applied to every root handler before the filter is added.
      When ``use_record_factory=True``, no ``ContextFilter`` is attached;
      context injection happens via the global ``LogRecordFactory`` instead.
    - **Standalone local development**: Adds a ``StreamHandler`` with
      ``ColorFormatter`` or ``JsonFormatter`` to the specified logger
      (or root logger if ``logger_name`` is None). Sets the level.
      Pass an explicit ``logger_name`` to avoid modifying the root logger.

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
        use_record_factory: When True, install the global ``LogRecordFactory``
            so context fields are injected at LogRecord creation time and are
            preserved through queued, delayed, or cross-thread handling. When
            this option is enabled, ``ContextFilter`` is **not** attached to
            handlers, because the global ``LogRecordFactory`` would be
            overwritten by the filter at handler dispatch time. Defaults to
            False to preserve the existing handler-filter-only behavior.
        extra_context_vars: Optional mapping of ``field_name -> ContextVar``
            whose current values ``ContextFilter`` also copies onto each
            LogRecord, alongside the four built-in context fields. Field names
            must not collide with the built-in fields. Only applies to the
            ``ContextFilter`` strategy (ignored when ``use_record_factory=True``).
        activate_trace_context: Sets the process-wide default that
            ``logging_context`` and ``with_context`` consult to attach the
            host's W3C trace context (via OpenTelemetry) — making OTel log
            records inherit the host span's ``trace_id``/``span_id``. Requires
            the ``[otel]`` extra; degrades to a silent no-op when OpenTelemetry
            is not installed. ``True``/``False`` force the default on/off; the
            default ``None`` selects the ``auto`` tier (enabled iff
            ``opentelemetry-api`` is importable). A per-call
            ``activate_trace_context`` argument overrides this default.

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

    set_default_trace_context_activation(activate_trace_context)

    # Install the global LogRecordFactory only after argument validation,
    # so an invalid call does not leave persistent global side effects.
    if use_record_factory:
        _install_context_factory()

    with _configured_lock:
        # When switching to record-factory mode, strip any previously-installed
        # ContextFilter from the target logger and root logger.  Must run BEFORE
        # the idempotency guards (so re-entry for the same logger_name still
        # removes stale filters), and UNDER _configured_lock (so concurrent
        # setup_logging() calls cannot race on the filter lists).
        if use_record_factory:
            _target = logging.getLogger(logger_name)
            _root = logging.getLogger()
            _remove_context_filters(_target)
            if _root is not _target:
                _remove_context_filters(_root)

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
            _state_key: _AzureStateKey = (logger_name, use_record_factory)
            if _state_key not in _azure_state:
                ctx_filter: ContextFilter | None = (
                    None if use_record_factory else ContextFilter(extra_context_vars)
                )
                _azure_state[_state_key] = (ctx_filter, weakref.WeakSet())
            context_filter, configured_handlers = _azure_state[_state_key]
            root = logging.getLogger()
            for handler in root.handlers:
                if handler in configured_handlers:
                    continue  # already configured — skip to avoid duplicates
                if functions_formatter is not None:
                    handler.setFormatter(functions_formatter)
                if context_filter is not None:
                    handler.addFilter(context_filter)
                configured_handlers.add(handler)
            # Install filter on root logger itself so handlers attached later
            # (before the next setup_logging() call) also inherit it.
            if context_filter is not None and context_filter not in root.filters:
                root.addFilter(context_filter)

            warn_host_json_level_conflict(level, host_json_path=host_json_path)
            warn_otel_logging_misconfig(
                functions_formatter=functions_formatter,
                host_json_path=host_json_path,
            )

        else:
            # Standalone local development: full idempotency via logger name.
            if logger_name in _configured_loggers:
                return

            # When the LogRecordFactory is active, attaching ContextFilter would
            # overwrite factory-injected fields at handler dispatch time.
            context_filter = None if use_record_factory else ContextFilter(extra_context_vars)
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
