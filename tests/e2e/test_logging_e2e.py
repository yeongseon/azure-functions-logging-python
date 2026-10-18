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
EXPECTED_VERSION = os.environ.get("E2E_EXPECTED_VERSION", "").strip()
APPINSIGHTS_NAME = os.environ.get("APPINSIGHTS_NAME", "")
APPINSIGHTS_RG = os.environ.get("E2E_RESOURCE_GROUP", "")
SKIP_REASON = "E2E_BASE_URL not set — skipping real-Azure e2e tests"
SKIP_AI_REASON = "APPINSIGHTS_NAME not set — skipping App Insights log query tests"
pytestmark = pytest.mark.e2e

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


def _extract_structured_fields(row: dict) -> dict | None:  # type: ignore[type-arg]
    """Extract invocation_id/function_name/cold_start/correlation_id from an
    App Insights traces row, recognizing both documented ingestion shapes
    (README): structured JSON retained whole in ``message``, or individual
    fields promoted into ``customDimensions``.

    Returns None only when NEITHER shape yields any parseable structured
    payload at all -- e.g. a plain, non-JSON message (#590's own repro). The
    caller is responsible for validating individual extracted field values;
    this function only reports whether a structured payload was found.
    """
    try:
        parsed = json.loads(row.get("message", ""))
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and "invocation_id" in parsed:
        extra = parsed.get("extra")
        return {
            "invocation_id": parsed.get("invocation_id"),
            "function_name": parsed.get("function_name"),
            "cold_start": parsed.get("cold_start"),
            "correlation_id": extra.get("correlation_id") if isinstance(extra, dict) else None,
        }

    custom_dimensions = row.get("customDimensions")
    if isinstance(custom_dimensions, str):
        try:
            custom_dimensions = json.loads(custom_dimensions)
        except json.JSONDecodeError:
            custom_dimensions = None
    if isinstance(custom_dimensions, dict) and "invocation_id" in custom_dimensions:
        return {
            "invocation_id": custom_dimensions.get("invocation_id"),
            "function_name": custom_dimensions.get("function_name"),
            "cold_start": custom_dimensions.get("cold_start"),
            "correlation_id": custom_dimensions.get("correlation_id"),
        }
    return None


@pytest.mark.skipif(not BASE_URL, reason=SKIP_REASON)
@pytest.mark.skipif(not APPINSIGHTS_NAME, reason=SKIP_AI_REASON)
def test_structured_log_appears_in_app_insights() -> None:
    """Invoke /api/logme and then poll App Insights until a row with
    structured invocation context matching our unique correlation ID
    appears -- not merely a row whose plain message happens to contain the
    correlation string (#590)."""
    # Ensure a fresh invocation with our unique correlation ID
    r = _get("/api/logme", correlation_id=CORRELATION_ID)
    assert r.status_code == 200

    # App Insights ingestion latency can be up to ~2-5 min
    query = (
        f"traces | where timestamp > ago(10m) | where message contains '{CORRELATION_ID}' "
        "| project message, customDimensions | limit 5"
    )
    deadline = time.time() + 360  # wait up to 6 minutes
    matched: dict | None = None  # type: ignore[type-arg]
    while time.time() < deadline:
        rows = _query_app_insights(query)
        for row in rows:
            fields = _extract_structured_fields(row)
            if fields is not None and fields.get("correlation_id") == CORRELATION_ID:
                matched = fields
                break
        if matched is not None:
            break
        time.sleep(15)
    else:
        pytest.fail(
            f"No row with structured fields matching correlation_id={CORRELATION_ID!r} "
            "appeared in App Insights within 6 minutes"
        )

    assert matched is not None
    assert matched["invocation_id"], "invocation_id must be present and non-empty"
    assert matched["function_name"] == "logme"
    assert isinstance(matched["cold_start"], bool)


@pytest.mark.skipif(not BASE_URL, reason=SKIP_REASON)
def test_deployed_version_matches_candidate() -> None:
    """Certify the deployed host runs the candidate wheel, not the PyPI build."""
    r = _get("/api/version")
    assert r.status_code == 200
    deployed = r.json()["version"]
    # Fail closed: when this test runs at all (BASE_URL is set), a missing/blank
    # E2E_EXPECTED_VERSION means the workflow wiring regressed and the
    # certification can no longer prove the deployed host ran the candidate wheel.
    assert EXPECTED_VERSION, (
        "E2E_EXPECTED_VERSION is not set — cannot certify that the deployed "
        "host runs the candidate wheel. Check the e2e-azure workflow wiring."
    )
    assert deployed == EXPECTED_VERSION, (
        f"Deployed version {deployed!r} != expected candidate "
        f"{EXPECTED_VERSION!r} — remote build did not install the "
        "bundled wheel"
    )
