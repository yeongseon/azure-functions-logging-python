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
    return category == "default" or category.startswith("Function")


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

        scope = "default" if category == "default" else f"category '{category}'"
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
    """Warn when a ``host.json`` ``logLevel`` entry suppresses logs below ``configured_level``.

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

    if host_path is not None:
        log_levels: object = None
        try:
            host_config: object = json.loads(host_path.read_text(encoding="utf-8"))
            host_mapping = _string_key_mapping(host_config)
            if host_mapping is not None:
                logging_mapping = _string_key_mapping(host_mapping.get("logging"))
                if logging_mapping is not None:
                    log_levels = logging_mapping.get("logLevel")
        except Exception:
            log_levels = None

        normalized_log_levels = _string_key_mapping(log_levels)
        if normalized_log_levels is not None:
            _warn_for_log_levels(
                normalized_log_levels,
                configured_level,
                strict=strict,
                source="host.json",
                stacklevel=3,
            )

    app_setting_log_levels = _iter_app_setting_log_levels()
    if app_setting_log_levels:
        _warn_for_log_levels(
            app_setting_log_levels,
            configured_level,
            strict=strict,
            source="AzureFunctionsJobHost app setting",
            stacklevel=3,
        )
