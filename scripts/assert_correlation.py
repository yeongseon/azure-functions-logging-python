#!/usr/bin/env python3
"""Assert the correlation claims from docs/how-correlation-works.md against a log.

Consumes the ``func`` host log produced by the host-boot matrix smoke after a
request to ``/api/correlation`` (see ``examples/e2e_app/function_app.py``) and
certifies three observable claims:

1. ``invocation_id`` on a bound record parses as a UUID (proto contract, §1–§2).
2. Two records from the same invocation share one ``invocation_id`` (§2).
3. A background thread *without* ``propagate_context`` loses the ``invocation_id``
   (§4, negative control) — proving the ``contextvars`` boundary is real.

The document is not the deliverable here; the *assertion* is. If any claim the
docs make stops being true on a real host, this script fails the smoke.

Usage:
    python scripts/assert_correlation.py <path-to-func-host.log>

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


def _extract_json_objects(text: str) -> list[dict[str, object]]:
    """Return every top-level JSON object embedded anywhere in *text*.

    The host prefixes worker log lines with its own text, so a record may not
    start at column 0. Scan for balanced ``{...}`` spans and keep the ones that
    parse as objects carrying our ``marker`` field.
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


def check(text: str) -> list[str]:
    """Return a list of failure messages (empty == all claims hold)."""
    records = _extract_json_objects(text)
    failures: list[str] = []

    main_1 = _find(records, MAIN_1)
    main_2 = _find(records, MAIN_2)
    thread = _find(records, THREAD)

    if main_1 is None:
        failures.append(f"no record found with marker '{MAIN_1}'")
    if main_2 is None:
        failures.append(f"no record found with marker '{MAIN_2}'")
    if thread is None:
        failures.append(f"no record found with marker '{THREAD}'")
    if failures:
        return failures

    assert main_1 is not None and main_2 is not None and thread is not None

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

    return failures


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path-to-func-host.log>", file=sys.stderr)
        return 2
    text = open(argv[1], encoding="utf-8", errors="replace").read()
    failures = check(text)
    if failures:
        print("Correlation certification FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(f"\nSee {DOC_URL} for the claims under test.", file=sys.stderr)
        return 1
    print("Correlation certification passed: all three claims hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
