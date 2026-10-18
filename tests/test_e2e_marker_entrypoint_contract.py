"""Regression tests for the E2E marker / entry-point contract (#588).

Most of these exercise the real pytest CLI contract via subprocess -- no
Azure resources or E2E_BASE_URL are required for any of them. The
guard-logic unit test loads tests/e2e/conftest.py directly under a
private module name (never "conftest") so it cannot collide with
pytest's own conftest discovery.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_e2e_conftest() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_e2e_conftest_under_test", REPO_ROOT / "tests" / "e2e" / "conftest.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_pytest(args: list[str], *, base_url: str | None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if base_url is None:
        env.pop("E2E_BASE_URL", None)
    else:
        env["E2E_BASE_URL"] = base_url
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestDedicatedE2eSelector:
    def test_collects_all_intended_e2e_tests(self) -> None:
        # Given no Azure deployment and no base URL -- collection only
        # When the dedicated certification selector is used
        result = _run_pytest(
            ["--collect-only", "-m", "e2e", "tests/e2e/", "--no-cov", "-q"],
            base_url=None,
        )

        # Then it collects the intended 4 real-host tests, not zero (#588)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "test_logging_e2e.py: 4" in result.stdout

    def test_without_base_url_fails_clearly_instead_of_silently_skipping(self) -> None:
        # Given E2E_BASE_URL is unset
        # When the dedicated certification selector actually runs (not
        # collect-only)
        result = _run_pytest(["-m", "e2e", "tests/e2e/", "--no-cov", "-q"], base_url=None)

        # Then it fails loudly with a clear configuration error -- an
        # entirely skipped suite must never look like a passing live run
        assert result.returncode != 0
        assert "E2E_BASE_URL is required" in (result.stdout + result.stderr)
        assert "4 skipped" not in result.stdout

    def test_with_base_url_but_no_appinsights_the_guard_does_not_fire(self) -> None:
        """Regression (#588): an intentional local-only App Insights
        omission (no APPINSIGHTS_NAME) must not trip the same hard-fail
        guard that catches a missing E2E_BASE_URL. Only
        test_structured_log_appears_in_app_insights skips on its own
        separate skipif in that scenario; the guard must not re-block the
        other three tests on APPINSIGHTS_NAME's absence.

        Calls the hook function directly (not a full subprocess run against
        a fake URL) so this stays fast and deterministic: a real run would
        otherwise block on the 120s health-check warmup retry loop before
        any test body executes, regardless of how quickly the connection
        is refused.
        """
        module = _load_e2e_conftest()
        config = SimpleNamespace(option=SimpleNamespace(collectonly=False, markexpr="e2e"))
        item = SimpleNamespace(get_closest_marker=lambda name: name == "e2e")

        with patch.dict(os.environ, {"E2E_BASE_URL": "http://localhost:7071"}, clear=False):
            try:
                module.pytest_collection_modifyitems(config, [item])
            except Exception as exc:  # pragma: no cover -- would only fire on a real bug
                pytest.fail(f"guard fired even though E2E_BASE_URL was set: {exc}")


class TestDefaultUnitSelector:
    def test_default_suite_still_excludes_e2e_tests(self) -> None:
        # Given the default marker exclusions (no explicit -m override)
        # When tests/e2e/ is collected without the dedicated selector
        result = _run_pytest(["--collect-only", "tests/e2e/", "--no-cov", "-q"], base_url=None)

        # Then nothing is selected -- e2e tests stay opt-in only (#588)
        assert result.returncode == 5
