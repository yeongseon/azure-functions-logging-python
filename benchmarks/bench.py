#!/usr/bin/env python3
"""Minimal, reproducible micro-benchmarks for azure-functions-logging.

Run with:

    python benchmarks/bench.py            # human-readable table
    python benchmarks/bench.py --json     # machine-readable JSON

Design goals (see issue #375):

- **Standalone.** Uses only the stdlib plus the package's own public API. No
  pytest, no third-party benchmark framework, no network, no Azure.
- **Reproducible.** Deterministic fake context, fixed iteration counts, warmup
  pass, and median-of-repeats reporting to damp scheduler noise.
- **Honest.** These are *in-process micro-benchmarks* of the hot paths this
  library adds. They measure CPU cost per operation on the machine running
  them; they say nothing about gRPC, host ingestion, or Application Insights.

The numbers are intentionally small in scope: import cost, setup cost, and the
per-record cost of context injection, JSON formatting, and the filters.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import gc
import json
import logging
import platform
import statistics
import sys
import time
from typing import Callable


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
class _FakeTraceContext:
    trace_parent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    trace_state = ""


class _FakeContext:
    """Duck-typed stand-in for azure.functions.Context (no azure dep needed)."""

    invocation_id = "706b8e5c-a630-4309-b815-6410526f237a"
    function_name = "bench_handler"
    trace_context = _FakeTraceContext()


def _make_record() -> logging.LogRecord:
    record = logging.LogRecord(
        name="bench",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Processing order %s",
        args=("o-42",),
        exc_info=None,
    )
    # A representative payload of structured extras.
    record.order_id = "o-42"  # type: ignore[attr-defined]
    record.user = {"id": "u-1", "password": "hunter2", "email": "a@b.com"}  # type: ignore[attr-defined]
    return record


# --------------------------------------------------------------------------- #
# Timing harness
# --------------------------------------------------------------------------- #
@dataclass
class Result:
    name: str
    iterations: int
    repeats: int
    median_ns_per_op: float
    min_ns_per_op: float

    def as_row(self) -> str:
        return f"{self.name:<38} {self.median_ns_per_op:>12,.0f} ns {self.min_ns_per_op:>12,.0f} ns"


def _time_once(fn: Callable[[], None], iterations: int) -> float:
    """Return ns/op for a single batch of ``iterations`` calls."""
    start = time.perf_counter_ns()
    for _ in range(iterations):
        fn()
    elapsed = time.perf_counter_ns() - start
    return elapsed / iterations


def bench(name: str, fn: Callable[[], None], *, iterations: int, repeats: int = 7) -> Result:
    fn()  # warmup / JIT-nothing but populate caches
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        samples = [_time_once(fn, iterations) for _ in range(repeats)]
    finally:
        if gc_was_enabled:
            gc.enable()
    return Result(
        name=name,
        iterations=iterations,
        repeats=repeats,
        median_ns_per_op=statistics.median(samples),
        min_ns_per_op=min(samples),
    )


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #
def bench_import() -> Result:
    """One-shot: cost of importing the package cold (subprocess-free estimate).

    We can't truly re-import into a clean interpreter here without a subprocess,
    so we measure ``importlib.reload`` of the top module as a proxy. Reported
    separately and labeled as a proxy.
    """
    import importlib

    import azure_functions_logging as pkg

    def _reload() -> None:
        importlib.reload(pkg)

    return bench(
        "import azure_functions_logging (reload proxy)", _reload, iterations=200, repeats=5
    )


def run_benchmarks() -> list[Result]:
    from azure_functions_logging import (
        JsonFormatter,
        RedactionFilter,
        SamplingFilter,
        inject_context,
        logging_context,
        restore_context,
        setup_logging,
    )

    results: list[Result] = []

    # setup_logging() — configure a dedicated named logger to avoid touching root.
    def _setup() -> None:
        setup_logging(logger_name="bench")

    results.append(bench("setup_logging(logger_name='bench')", _setup, iterations=2_000, repeats=5))

    ctx = _FakeContext()

    # inject_context() + restore_context() round trip (per warm invocation).
    def _inject_restore() -> None:
        tokens = inject_context(ctx)
        restore_context(tokens)

    results.append(bench("inject_context + restore_context", _inject_restore, iterations=50_000))

    # logging_context() context manager (recommended primary path).
    def _logging_context() -> None:
        with logging_context(ctx):
            pass

    results.append(
        bench("logging_context(context) enter/exit", _logging_context, iterations=50_000)
    )

    # JsonFormatter.format() per record.
    json_formatter = JsonFormatter()
    json_record = _make_record()

    def _json_format() -> None:
        json_formatter.format(json_record)

    results.append(bench("JsonFormatter.format(record)", _json_format, iterations=50_000))

    # SamplingFilter.filter() per record (high rate so nothing is dropped).
    sampling = SamplingFilter(rate=1_000_000, window=1.0)
    sample_record = _make_record()

    def _sampling() -> None:
        sampling.filter(sample_record)

    results.append(bench("SamplingFilter.filter(record)", _sampling, iterations=100_000))

    # RedactionFilter.filter() per record (with a nested sensitive payload).
    redaction = RedactionFilter()

    def _redaction() -> None:
        redaction.filter(_make_record())

    results.append(
        bench("RedactionFilter.filter(record) [new record]", _redaction, iterations=50_000)
    )

    return results


def _environment() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--include-import",
        action="store_true",
        help="also run the import-reload proxy benchmark (noisy)",
    )
    args = parser.parse_args()

    # Silence actual log output during benchmarking.
    logging.getLogger("bench").handlers.clear()
    logging.getLogger("bench").addHandler(logging.NullHandler())

    results = run_benchmarks()
    if args.include_import:
        results.append(bench_import())

    env = _environment()

    if args.json:
        print(json.dumps({"environment": env, "results": [asdict(r) for r in results]}, indent=2))
        return 0

    print("azure-functions-logging — micro-benchmarks")
    print(
        f"  {env['implementation']} {env['python']} on {env['platform']}\n"
        f"  (in-process CPU cost per op; excludes gRPC / host / ingestion)\n"
    )
    print(f"{'benchmark':<38} {'median':>15} {'min':>15}")
    print("-" * 70)
    for r in results:
        print(r.as_row())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
