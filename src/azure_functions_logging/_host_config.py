"""host.json logging configuration helpers."""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging
import os
from pathlib import Path
import warnings

_HOST_LEVEL_TO_LOGGING: dict[str, int] = {
    "critical": logging.CRITICAL,
    "debug": logging.DEBUG,
    "error": logging.ERROR,
    "information": logging.INFO,
    "none": logging.CRITICAL + 10,
    "trace": logging.DEBUG,
    "warning": logging.WARNING,
}

# Maximum number of parent directories to walk when auto-discovering host.json.
# Bounded to avoid scanning the entire filesystem on misconfigured environments.
_HOST_JSON_DISCOVERY_MAX_DEPTH = 5
_HOST_JSON_ENV_PREFIX = "AzureFunctionsJobHost__logging__logLevel__"


def _resolve_host_level(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    return _HOST_LEVEL_TO_LOGGING.get(value.lower())


def discover_host_json(start: Path | None = None) -> Path | None:
    """Locate ``host.json`` deterministically by walking ``start`` upward.

    Discovery order:

    1. ``start`` (when supplied). If ``start.resolve()`` fails, returns ``None``
       immediately; env var and cwd fallback are not attempted.
    2. ``AzureWebJobsScriptRoot`` environment variable (only when ``start`` is
       ``None``). Only the directory itself is probed — no ancestor walk. Relative
       values are resolved against cwd (Azure always sets an absolute path).
    3. :func:`Path.cwd` and each ancestor up to
       :data:`_HOST_JSON_DISCOVERY_MAX_DEPTH` levels (fallback when neither
       ``start`` nor the env var resolves to a file).
    Returns the first existing ``host.json`` path or ``None``. Never raises:
    filesystem errors are swallowed so callers stay silent on broken setups.
    """
    try:
        base = start.resolve() if start is not None else None
    except Exception:
        return None

    if base is None:
        env_root = os.environ.get("AzureWebJobsScriptRoot")
        if env_root:
            try:
                env_candidate = Path(env_root).resolve() / "host.json"
                if env_candidate.is_file():
                    return env_candidate
            except (OSError, RuntimeError):
                pass  # invalid path — fall through to cwd walk
        try:
            base = Path.cwd().resolve()
        except Exception:
            return None

    candidates = [base, *list(base.parents)[:_HOST_JSON_DISCOVERY_MAX_DEPTH]]
    for directory in candidates:
        candidate = directory / "host.json"
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


# Categories that directly affect user application logs.
# Warnings are limited to these prefixes by default.
# Host-internal categories (Host.Results, Host.Aggregator, etc.) are
# excluded because they do not suppress user Python log output.
_USER_RELEVANT_PREFIXES: tuple[str, ...] = ("default", "Function")


def _is_user_relevant_category(category: str) -> bool:
    """Return True for categories that can suppress user application logs."""
    return category.lower() == "default" or category.startswith("Function")


def _iter_app_setting_log_levels() -> dict[str, str]:
    levels: dict[str, str] = {}
    prefix_len = len(_HOST_JSON_ENV_PREFIX)
    for key, value in os.environ.items():
        if not key.startswith(_HOST_JSON_ENV_PREFIX):
            continue
        category_parts = [part for part in key[prefix_len:].split("__") if part]
        if not category_parts:
            continue
        category = ".".join(category_parts)
        levels[category] = value
    return levels


def _warn_for_log_levels(
    log_levels: Mapping[str, object],
    configured_level: int,
    *,
    strict: bool,
    source: str,
    stacklevel: int,
) -> None:
    configured_level_name = logging.getLevelName(configured_level)

    for category, raw_level in log_levels.items():
        if not strict and not _is_user_relevant_category(category):
            continue
        resolved_level = _resolve_host_level(raw_level)
        if resolved_level is None:
            continue
        if resolved_level <= configured_level:
            continue

        scope = "default" if category.lower() == "default" else f"category '{category}'"
        warnings.warn(
            (
                f"{source} logLevel for {scope} is set to '{raw_level}' which is more "
                f"restrictive than the configured level '{configured_level_name}'. Logs "
                f"below '{raw_level}' will be suppressed by the Azure Functions host."
            ),
            stacklevel=stacklevel,
        )


def _string_key_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key: object = raw_key
        item: object = raw_value
        if isinstance(key, str):
            result[key] = item
    return result


def warn_host_json_level_conflict(
    configured_level: int,
    *,
    host_json_path: Path | str | None = None,
    strict: bool = False,
) -> None:
    """Warn when a ``host.json`` or app-setting ``logLevel`` entry suppresses logs.

    Fires when an effective log level is more restrictive than ``configured_level``.

    Effective log levels are computed by merging host.json with
    ``AzureFunctionsJobHost__logging__logLevel__*`` app settings (app settings
    take precedence per-category, matching Azure Functions runtime behavior).

    By default only user-relevant categories are checked (``default`` and anything
    starting with ``Function``). Host-internal categories (``Host.Results``,
    ``Host.Aggregator``, etc.) are skipped because they cannot suppress user Python
    log output and generate false-positive warning fatigue.

    Args:
        configured_level: The numeric logging level configured by the app.
        host_json_path: Optional explicit path to a ``host.json`` file. When
            provided, auto-discovery is bypassed entirely. When ``None``,
            :func:`discover_host_json` is used.
        strict: When ``True``, all categories are inspected (including
            host-internal ones). Default: ``False``.
    """
    host_path: Path | None
    if host_json_path is not None:
        host_path = Path(host_json_path)
        try:
            if not host_path.is_file():
                host_path = None
        except OSError:
            host_path = None
    else:
        discovered = discover_host_json()
        host_path = discovered

    # Collect host.json log levels
    host_json_log_levels: dict[str, object] = {}
    if host_path is not None:
        try:
            host_config: object = json.loads(host_path.read_text(encoding="utf-8"))
            host_mapping = _string_key_mapping(host_config)
            if host_mapping is not None:
                logging_mapping = _string_key_mapping(host_mapping.get("logging"))
                if logging_mapping is not None:
                    raw_levels = _string_key_mapping(logging_mapping.get("logLevel"))
                    if raw_levels is not None:
                        host_json_log_levels = raw_levels
        except Exception:  # nosec B110 — host.json read failure is non-fatal
            pass

    # Collect app setting overrides
    app_setting_log_levels = _iter_app_setting_log_levels()

    # Merge: app settings override host.json per category (runtime precedence).
    # Normalize 'default'/'Default' to lowercase for consistent merging.
    # Only allow recognized app-setting values to override; unrecognized values
    # (e.g. typos) must not mask a restrictive host.json entry.
    normalized_host: dict[str, object] = {
        (k.lower() if k.lower() == "default" else k): v for k, v in host_json_log_levels.items()
    }
    normalized_app: dict[str, object] = {}
    for k, v in app_setting_log_levels.items():
        norm_k = k.lower() if k.lower() == "default" else k
        if _resolve_host_level(v) is not None:
            normalized_app[norm_k] = v
        # else: unrecognized value — do not override host.json entry

    effective_levels: dict[str, object] = {**normalized_host, **normalized_app}

    if not effective_levels:
        return

    _warn_for_log_levels(
        effective_levels,
        configured_level,
        strict=strict,
        source="host configuration",
        stacklevel=3,
    )


def _has_otel_logging_handler(logger: logging.Logger) -> bool:
    """Return True if *logger* has an OpenTelemetry logging handler attached.

    Detection is **import-free**: it inspects each handler's defining module
    name rather than importing OpenTelemetry. This covers both
    ``opentelemetry.sdk._logs`` and ``opentelemetry.instrumentation.logging``
    handlers, and stays a no-op when OpenTelemetry is not installed.
    """
    for handler in logger.handlers:
        module = type(handler).__module__ or ""
        if module.startswith("opentelemetry."):
            return True
    return False


def _any_otel_logging_handler() -> bool:
    """Return True if an OpenTelemetry logging handler is attached anywhere in
    the active logger hierarchy, not just on the root logger.

    ``configure_azure_monitor()`` attaches its handler to the root logger, but a
    self-managed OpenTelemetry setup may attach the ``LoggingHandler`` to a
    named child logger instead. Scanning the manager's ``loggerDict`` avoids a
    false "no handler" verdict (and a spurious 6c warning) in that case.
    """
    if _has_otel_logging_handler(logging.getLogger()):
        return True
    for obj in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(obj, logging.Logger) and _has_otel_logging_handler(obj):
            return True
    return False


def _read_host_telemetry_mode(host_json_path: Path | str | None) -> str | None:
    """Return the ``telemetryMode`` string from ``host.json``, or ``None``.

    Uses the same discovery rules as :func:`warn_host_json_level_conflict`.
    Never raises: any read/parse failure yields ``None``.
    """
    host_path: Path | None
    if host_json_path is not None:
        host_path = Path(host_json_path)
        try:
            if not host_path.is_file():
                return None
        except OSError:
            return None
    else:
        host_path = discover_host_json()
    if host_path is None:
        return None
    try:
        host_config: object = json.loads(host_path.read_text(encoding="utf-8"))
        host_mapping = _string_key_mapping(host_config)
        if host_mapping is None:
            return None
        mode = host_mapping.get("telemetryMode")
        return mode if isinstance(mode, str) else None
    except Exception:  # nosec B110 — host.json read failure is non-fatal
        return None


# App settings that signal the host will export OpenTelemetry logs. Microsoft
# docs reference both names (likely a mid-rename), so either being set counts.
_OTEL_TELEMETRY_ENV_VARS: tuple[str, ...] = (
    "PYTHON_ENABLE_OPENTELEMETRY",
    "PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY",
)


# Generic OpenTelemetry SDK export settings. Their presence signals the user
# is managing OTel export themselves (e.g. OTLP straight to a collector), so a
# missing Azure-specific telemetry env var is not necessarily a misconfig.
_OTEL_GENERIC_EXPORT_ENV_VARS: tuple[str, ...] = (
    "OTEL_LOGS_EXPORTER",
    "OTEL_TRACES_EXPORTER",
)


# Azure Monitor export settings. ``configure_azure_monitor()`` wires its
# exporter from ``APPLICATIONINSIGHTS_CONNECTION_STRING`` and does not set any
# ``PYTHON_*`` or ``OTEL_*_EXPORTER`` variable, so on the Microsoft-documented
# ``configure_azure_monitor()`` -> ``setup_logging()`` path these logs are in
# fact exported. Treat a connection string as a "user manages export" signal so
# 6b does not cry wolf (issue #303).
_AZURE_MONITOR_EXPORT_ENV_VARS: tuple[str, ...] = (
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "AZURE_MONITOR_CONNECTION_STRING",
)


def warn_otel_logging_misconfig(
    *,
    functions_formatter: logging.Formatter | None = None,
    host_json_path: Path | str | None = None,
    stacklevel: int = 3,
) -> None:
    """Warn on common OpenTelemetry logging misconfigurations (issue #256).

    These checks run at ``setup_logging()`` call time and assume the documented
    call order: ``configure_azure_monitor()`` **before** ``setup_logging()`` so
    the OpenTelemetry ``LoggingHandler`` is already attached to the root logger.

    Emits up to three independent warnings:

    - **6a** — an OTel handler is present **and** ``functions_formatter`` was
      passed: the OTel handler formats and exports its own records, so the
      formatter does not affect what OpenTelemetry emits. It still applies to
      any non-OTel handler that coexists on the root logger, so this is a
      heads-up rather than an absolute "formatter has no effect" claim.
    - **6b** — an OTel handler is present but no export signal is observable
      (no telemetry env var, no generic OTLP exporter, and no Azure Monitor
      connection string): the host may not export these logs. Worded
      tentatively because the environment is not fully observable from inside
      the worker.
    - **6c** — ``host.json`` requests ``telemetryMode: OpenTelemetry`` but no
      OTel handler is attached: most often a call-order mistake. Worded as an
      ordering hint rather than a definitive "worker unconfigured" claim, so it
      does not cry wolf when the handler is simply attached later.
    """
    has_otel_handler = _any_otel_logging_handler()

    # 6a: OTel handler present AND a functions_formatter was supplied.
    if has_otel_handler and functions_formatter is not None:
        warnings.warn(
            (
                "An OpenTelemetry logging handler is attached; the "
                "'functions_formatter' passed to setup_logging() does not "
                "affect what OpenTelemetry exports — the OpenTelemetry handler "
                "formats and exports its records itself. It still applies to "
                "any non-OpenTelemetry handler on the root logger."
            ),
            stacklevel=stacklevel,
        )

    # 6b: OTel handler present but no export signal is observable (tentative).
    if has_otel_handler and not any(
        os.environ.get(name)
        for name in (
            *_OTEL_TELEMETRY_ENV_VARS,
            *_OTEL_GENERIC_EXPORT_ENV_VARS,
            *_AZURE_MONITOR_EXPORT_ENV_VARS,
        )
    ):
        joined = " or ".join(_OTEL_TELEMETRY_ENV_VARS)
        warnings.warn(
            (
                "An OpenTelemetry logging handler is attached but neither "
                f"{joined} appears to be set. Depending on your host "
                "configuration, these logs may not be exported — verify your "
                "telemetry settings."
            ),
            stacklevel=stacklevel,
        )

    # 6c: host.json requests OpenTelemetry mode but no OTel handler detected.
    if not has_otel_handler:
        mode = _read_host_telemetry_mode(host_json_path)
        if mode is not None and mode.lower() == "opentelemetry":
            warnings.warn(
                (
                    "host.json sets telemetryMode 'OpenTelemetry' but no "
                    "OpenTelemetry logging handler is attached yet. If you use "
                    "configure_azure_monitor(), call it before setup_logging() "
                    "so filters and context land on the OpenTelemetry handler."
                ),
                stacklevel=stacklevel,
            )
