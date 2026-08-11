"""Resolve a stable worker-instance identifier for scaled-out Azure Functions.

Azure Functions is serverless and scales out across worker instances. To let
logs be attributed to the instance that produced them, this module resolves a
``host_instance_id`` from platform-provided environment variables, mirroring the
Azure Functions host's own instance-id logic
(``EnvironmentExtensions.GetInstanceId``) and the OpenTelemetry Azure detector's
``faas.instance`` precedence:

    ``WEBSITE_INSTANCE_ID`` → ``WEBSITE_POD_NAME`` → ``CONTAINER_NAME``
    → ``socket.gethostname()``

``WEBSITE_INSTANCE_ID`` is present on App Service / Dedicated / Elastic Premium /
Windows Consumption, but is typically **absent** on Linux/Flex Consumption and
container-based hosting, where the host uses ``WEBSITE_POD_NAME`` /
``CONTAINER_NAME`` instead. ``socket.gethostname()`` is a last-resort fallback so
local and non-Azure deployments still get a value.

The resolved value is cached per process and keyed on the current PID, so a
forked worker (a pattern used on some Consumption plans) recomputes its own
identity instead of inheriting the parent's cached value. Resolution never
raises: on total failure the value is ``None`` (Principle 3: logging metadata
must never crash the application).
"""

from __future__ import annotations

import os
import socket

#: Environment variables consulted, in priority order, before falling back to
#: :func:`socket.gethostname`. Order matches the Azure Functions host's
#: ``GetInstanceId`` and the OpenTelemetry Azure ``faas.instance`` detector.
_INSTANCE_ENV_VARS: tuple[str, ...] = (
    "WEBSITE_INSTANCE_ID",
    "WEBSITE_POD_NAME",
    "CONTAINER_NAME",
)

# Per-process cache. Keyed on the PID that computed it so that a forked child
# recomputes instead of reusing the parent's value.
_cached_pid: int | None = None
_cached_value: str | None = None


def _resolve_host_instance_id() -> str | None:
    """Resolve the instance id from the environment, never raising.

    Tries each variable in :data:`_INSTANCE_ENV_VARS` in order, then
    ``socket.gethostname()``. Returns the first non-empty value, or ``None`` if
    every source is empty or unavailable.
    """
    try:
        for name in _INSTANCE_ENV_VARS:
            value = os.environ.get(name)
            if value:
                return value
        hostname = socket.gethostname()
        return hostname or None
    except Exception:  # nosec B110 — Principle 3: metadata resolution is silent
        return None


def get_host_instance_id() -> str | None:
    """Return the cached ``host_instance_id`` for the current process.

    The value is computed once per process (lazily, on first call) and reused
    for the process lifetime. The cache is keyed on ``os.getpid()`` so a forked
    child transparently recomputes its own identity.

    Returns:
        The resolved instance identifier, or ``None`` when no source yields a
        value (resolution is fully fail-safe and never raises).
    """
    global _cached_pid, _cached_value
    current_pid = os.getpid()
    if _cached_pid != current_pid:
        _cached_value = _resolve_host_instance_id()
        _cached_pid = current_pid
    return _cached_value


def _reset_host_instance_id_cache() -> None:
    """Clear the per-process cache. Intended for test isolation only."""
    global _cached_pid, _cached_value
    _cached_pid = None
    _cached_value = None
