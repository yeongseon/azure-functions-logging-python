#!/usr/bin/env python3
"""Assert the correlation claims from the public "How correlation works" docs against a log.

Consumes the ``func`` host log and HTTP response produced by the host-boot
matrix smoke after a request to ``/api/correlation`` (see
``examples/e2e_app/function_app.py``) and certifies four observable claims (documented at
``https://yeongseon.dev/azure-functions-python/logging/how-correlation-works/``):

1. ``invocation_id`` on a bound record parses as a UUID (proto contract, §1–§2).
2. Two records from the same invocation share one ``invocation_id`` (§2).
3. A background thread *without* ``propagate_context`` loses the ``invocation_id``
   (§4, negative control) — proving the ``contextvars`` boundary is real.
4. A background thread *with* ``propagate_context`` keeps the invocation id
   (§4, positive control).

The document is not the deliverable here; the *assertion* is. If any claim the
docs make stops being true on a real host, this script fails the smoke.

Usage:
    python scripts/assert_correlation.py <path-to-func-host.log> <path-to-response.json>

Stdlib-only on purpose. Exit code 0 = all claims hold, 1 = a claim failed.
"""

from __future__ import annotations

import json
import sys
from uuid import UUID

DOC_URL = "https://yeongseon.dev/azure-functions-python/logging/how-correlation-works/"

# Markers emitted by the /api/correlation endpoint.
MAIN_1 = "corr-main-1"
MAIN_2 = "corr-main-2"
THREAD = "corr-thread-unpropagated"
PROPAGATED_THREAD = "corr-thread-propagated"


def _extract_json_objects(text: str) -> list[dict[str, object]]:
    """Return every top-level JSON object embedded anywhere in *text*.

    The host prefixes worker log lines with its own text, so a record may not
    start at column 0. Scan for balanced ``{...}`` spans and keep every span that
    parses as a JSON object; callers filter by ``marker`` via :func:`_find`.
    """
    objects: list[dict[str, object]] = []
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    chunk = text[start : i + 1]
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        pass
                    else:
                        if isinstance(obj, dict):
                            objects.append(obj)
                    start = -1
    return objects


def _marker(record: dict[str, object]) -> str | None:
    extra = record.get("extra")
    if isinstance(extra, dict):
        marker = extra.get("marker")
        if isinstance(marker, str):
            return marker
    marker = record.get("marker")
    return marker if isinstance(marker, str) else None


def _find(records: list[dict[str, object]], marker: str) -> dict[str, object] | None:
    for record in records:
        if _marker(record) == marker:
            return record
    return None


def _thread_records(response_text: str) -> list[dict[str, object]]:
    response_objects = _extract_json_objects(response_text)
    if not response_objects:
        return []
    records = response_objects[0].get("thread_records")
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def check(host_text: str, response_text: str) -> list[str]:
    """Return a list of failure messages (empty == all claims hold)."""
    records = _extract_json_objects(host_text)
    response_records = _thread_records(response_text)
    failures: list[str] = []

    main_1 = _find(records, MAIN_1)
    main_2 = _find(records, MAIN_2)
    thread = _find(response_records, THREAD)
    propagated_thread = _find(records, PROPAGATED_THREAD)

    if main_1 is None:
        failures.append(f"no record found with marker '{MAIN_1}'")
    if main_2 is None:
        failures.append(f"no record found with marker '{MAIN_2}'")
    if thread is None:
        failures.append(f"no record found with marker '{THREAD}'")
    if propagated_thread is None:
        failures.append(f"no record found with marker '{PROPAGATED_THREAD}'")
    if failures:
        return failures

    assert main_1 is not None and main_2 is not None
    assert thread is not None and propagated_thread is not None

    # Claim 1: invocation_id parses as a UUID.
    inv_1 = main_1.get("invocation_id")
    if not isinstance(inv_1, str):
        failures.append(f"'{MAIN_1}' has no string invocation_id: {inv_1!r}")
    else:
        try:
            UUID(inv_1)
        except ValueError:
            failures.append(f"'{MAIN_1}' invocation_id is not a UUID: {inv_1!r}")

    # Claim 2: both main-thread records share the same invocation_id.
    inv_2 = main_2.get("invocation_id")
    if inv_1 != inv_2:
        failures.append(
            f"invocation_id differs within one invocation: {MAIN_1}={inv_1!r} vs {MAIN_2}={inv_2!r}"
        )

    # Claim 3: the unpropagated background-thread record has no invocation_id.
    inv_thread = thread.get("invocation_id")
    if inv_thread not in (None, ""):
        failures.append(
            f"'{THREAD}' unexpectedly carried an invocation_id ({inv_thread!r}); "
            f"a background thread without propagate_context must lose it"
        )

    inv_propagated = propagated_thread.get("invocation_id")
    if inv_propagated != inv_1:
        failures.append(
            f"'{PROPAGATED_THREAD}' invocation_id differs from the request: "
            f"{inv_propagated!r} != {inv_1!r}"
        )

    return failures


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            f"usage: {argv[0]} <path-to-func-host.log> <path-to-response.json>",
            file=sys.stderr,
        )
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as fh:
        host_text = fh.read()
    with open(argv[2], encoding="utf-8", errors="replace") as fh:
        response_text = fh.read()
    failures = check(host_text, response_text)
    if failures:
        print("Correlation certification FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(f"\nSee {DOC_URL} for the claims under test.", file=sys.stderr)
        return 1
    print("Correlation certification passed: all four claims hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
