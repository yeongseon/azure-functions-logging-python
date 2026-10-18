"""Guard rail for the dedicated real-Azure E2E certification entry point.

Without this guard, invoking the dedicated ``-m e2e`` selector (the Hatch
``e2e-azure`` task / Makefile ``e2e-local``/``e2e-azure`` targets / the
Azure certification workflow) with ``E2E_BASE_URL`` unset would silently
skip all 4 real-host tests via their own ``skipif`` guards and exit 0 --
indistinguishable from a successful live verification (#588). Fail loudly
instead: a dedicated certification run with no base URL is a configuration
error, not a pass.

Deliberately does NOT gate on ``APPINSIGHTS_NAME``: a local run against
Azurite (``make e2e-local``) has no real Application Insights instance to
query, so ``test_structured_log_appears_in_app_insights`` skipping on its
own, separate ``skipif``, while the other three tests still run, is an
intentional, documented local-only omission -- not the all-skipped failure
mode this guard exists to catch.
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.option.collectonly:
        # Collection-only runs (e.g. the issue's own repro command, or CI
        # dry-run checks) must never require a live base URL.
        return
    markexpr = (config.option.markexpr or "").strip()
    if markexpr != "e2e":
        # Not the dedicated certification selector (e.g. the default unit
        # suite runs with "not e2e" and never reaches here with e2e items
        # to begin with).
        return
    if not any(item.get_closest_marker("e2e") for item in items):
        return
    if os.environ.get("E2E_BASE_URL"):
        return
    pytest.exit(
        "E2E_BASE_URL is required to run tests/e2e with the dedicated "
        "'-m e2e' selector. An unset E2E_BASE_URL must not be mistaken for "
        "a passing live Azure verification (#588).",
        returncode=1,
    )
