"""host.json logging configuration helpers."""

from __future__ import annotations

import json
import os
import logging
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


def _resolve_host_level(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    return _HOST_LEVEL_TO_LOGGING.get(value.lower())


def discover_host_json(start: Path | None = None) -> Path | None:
    """Locate ``host.json`` deterministically by walking ``start`` upward.

    Discovery order:

    1. ``start`` (when supplied).
    2. ``AzureWebJobsScriptRoot`` environment variable (only when ``start`` is
       ``None``).
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
            except OSError:
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
    if host_json_path is not None:
        host_path = Path(host_json_path)
        try:
            if not host_path.is_file():
                return
        except OSError:
            return
    else:
        discovered = discover_host_json()
        if discovered is None:
            return
        host_path = discovered

    try:
        host_config = json.loads(host_path.read_text(encoding="utf-8"))
    except Exception:
        return

    try:
        log_levels = host_config["logging"]["logLevel"]
    except Exception:
        return

    if not isinstance(log_levels, dict):
        return

    configured_level_name = logging.getLevelName(configured_level)

    for category, raw_level in log_levels.items():
        if not isinstance(category, str):
            continue
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
                f"host.json logLevel for {scope} is set to '{raw_level}' which is more "
                f"restrictive than the configured level '{configured_level_name}'. Logs "
                f"below '{raw_level}' will be suppressed by the Azure Functions host."
            ),
            stacklevel=3,
        )
