"""E2E tests for azure-functions-logging on a real Azure Functions host.

Two test groups:
1. HTTP-level: invoke /api/logme, verify 200 response.
2. App Insights: query traces table and assert structured JSON fields appear.
   Requires APPINSIGHTS_APP_ID and APPINSIGHTS_API_KEY (or AZURE_CLIENT_ID
   for OIDC-based query via az CLI).

Usage:
    E2E_BASE_URL=https://<app>.azurewebsites.net \\
    APPINSIGHTS_NAME=<ai-name> \\
    pytest tests/e2e -v
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import pytest
import requests

BASE_URL = os.environ.get("E2E_BASE_URL", "").rstrip("/")
APPINSIGHTS_NAME = os.environ.get("APPINSIGHTS_NAME", "")
APPINSIGHTS_RG = os.environ.get("E2E_RESOURCE_GROUP", "")
SKIP_REASON = "E2E_BASE_URL not set — skipping real-Azure e2e tests"
SKIP_AI_REASON = "APPINSIGHTS_NAME not set — skipping App Insights log query tests"

CORRELATION_ID = f"e2e-{int(time.time())}"


def _get(path: str, **params: str) -> requests.Response:
    return requests.get(f"{BASE_URL}{path}", params=params, timeout=30)


@pytest.fixture(scope="session", autouse=True)
def warmup() -> None:
    if not BASE_URL:
        return
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=10)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    pytest.fail("Warmup failed: /api/health did not respond within 120 s")


# ── HTTP-level tests ───────────────────────────────────────────────────────


@pytest.mark.skipif(not BASE_URL, reason=SKIP_REASON)
def test_health_returns_200() -> None:
    r = _get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.skipif(not BASE_URL, reason=SKIP_REASON)
def test_logme_returns_200_with_correlation_id() -> None:
    r = _get("/api/logme", correlation_id=CORRELATION_ID)
    assert r.status_code == 200
    body = r.json()
    assert body["logged"] is True
    assert body["correlation_id"] == CORRELATION_ID


# ── App Insights log query tests ───────────────────────────────────────────


def _query_app_insights(query: str) -> list[dict]:  # type: ignore[type-arg]
    """Run a Kusto query against App Insights via az CLI and return rows."""
    result = subprocess.run(
        [
            "az",
            "monitor",
            "app-insights",
            "query",
            "--app",
            APPINSIGHTS_NAME,
            "--resource-group",
            APPINSIGHTS_RG,
            "--analytics-query",
            query,
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"az query failed: {result.stderr}")
    data = json.loads(result.stdout)
    tables = data.get("tables", [])
    if not tables:
        return []
    rows = tables[0].get("rows", [])
    cols = [c["name"] for c in tables[0].get("columns", [])]
    return [dict(zip(cols, row)) for row in rows]


@pytest.mark.skipif(not BASE_URL, reason=SKIP_REASON)
@pytest.mark.skipif(not APPINSIGHTS_NAME, reason=SKIP_AI_REASON)
def test_structured_log_appears_in_app_insights() -> None:
    """Invoke /api/logme and then poll App Insights until the log entry appears."""
    # Ensure a fresh invocation with our unique correlation ID
    r = _get("/api/logme", correlation_id=CORRELATION_ID)
    assert r.status_code == 200

    # App Insights ingestion latency can be up to ~2-5 min
    query = (
        f"traces | where timestamp > ago(10m) | where message contains '{CORRELATION_ID}' | limit 5"
    )
    deadline = time.time() + 360  # wait up to 6 minutes
    while time.time() < deadline:
        rows = _query_app_insights(query)
        if rows:
            break
        time.sleep(15)
    else:
        pytest.fail(
            f"Structured log with correlation_id={CORRELATION_ID!r} "
            "did not appear in App Insights within 6 minutes"
        )

    assert len(rows) > 0
    row = rows[0]
    assert CORRELATION_ID in row.get("message", "")
