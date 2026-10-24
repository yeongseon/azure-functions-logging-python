"""Opt-in strict-skip policy for CI lanes that must not silently shrink.

With ``FAIL_ON_SKIP=1`` a session that reported any skip exits non-zero: skipped tests,
module-level ``importorskip``, ``xfail`` (pytest reports it as skipped) and skipped
setup/teardown. A session that already failed or selected nothing keeps its exit code.

It is off by default: the offline unit suite has legitimate version-dependent skips. Only
the Azure certification step (``e2e-azure.yml``) and the OpenTelemetry upstream canary
(``otel-nightly.yml``) enable it, where a skip would hide a regression.
"""

from __future__ import annotations

import os

import pytest

_skipped: list[str] = []


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.skipped:
        _skipped.append(report.nodeid)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped:
        _skipped.append(report.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if os.environ.get("FAIL_ON_SKIP") == "1" and _skipped and exitstatus == 0:
        print(f"\nFAIL_ON_SKIP=1: {len(_skipped)} skipped item(s) in a lane that forbids skips")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
