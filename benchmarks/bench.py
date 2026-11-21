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
from collections.abc import Callable
from dataclasses import asdict, dataclass
import gc
import json
import logging
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


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
    record.user = {"id": "u-1", "password": "hunter2", "email": "a@b.com"}  # type: ignore[attr-defined] # nosec B105 - fake password; the benchmark measures masking
    return record


class _NullSinkHandler(logging.Handler):
    """Handler that formats each record and discards it (no I/O, no network)."""

    def emit(self, record: logging.LogRecord) -> None:
        self.format(record)


class _MemorySinkHandler(logging.Handler):
    """Handler that formats each record into a list: an in-memory sink, no I/O."""

    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.payloads.append(self.format(record))


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
    stdev_ns_per_op: float = 0.0

    def as_row(self) -> str:
        return (
            f"{self.name:<50} {self.median_ns_per_op:>11,.0f} ns "
            f"±{self.stdev_ns_per_op:>9,.0f} ns {self.min_ns_per_op:>11,.0f} ns"
        )


def _time_once(
    fn: Callable[[], None],
    iterations: int,
    before: Callable[[], None] | None = None,
) -> float:
    """Return ns/op for a batch of ``iterations`` calls.

    When ``before`` is provided it runs untimed before each call — used to reset
    state (e.g. so ``setup_logging`` measures first-time cost, not its idempotent
    fast-path) without charging the reset to the measurement.
    """
    if before is None:
        start = time.perf_counter_ns()
        for _ in range(iterations):
            fn()
        return (time.perf_counter_ns() - start) / iterations

    total = 0
    for _ in range(iterations):
        before()
        start = time.perf_counter_ns()
        fn()
        total += time.perf_counter_ns() - start
    return total / iterations


def bench(
    name: str,
    fn: Callable[[], None],
    *,
    iterations: int,
    repeats: int = 7,
    before: Callable[[], None] | None = None,
) -> Result:
    if before is not None:
        before()
    fn()  # warmup / populate caches
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        samples = [_time_once(fn, iterations, before) for _ in range(repeats)]
    finally:
        if gc_was_enabled:
            gc.enable()
    return Result(
        name=name,
        iterations=iterations,
        repeats=repeats,
        median_ns_per_op=statistics.median(samples),
        min_ns_per_op=min(samples),
        stdev_ns_per_op=statistics.stdev(samples) if len(samples) > 1 else 0.0,
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

    # setup_logging() first-time configuration cost. Without resetting state, the
    # idempotency guard (_configured_loggers) would short-circuit every call after
    # warmup and we'd measure re-entry, not real configuration. The reset runs
    # untimed via ``before`` so only setup_logging() itself is measured.
    import azure_functions_logging._setup as _setup_mod

    def _reset_setup_state() -> None:
        _setup_mod._configured_loggers.discard("bench")
        lgr = logging.getLogger("bench")
        lgr.handlers.clear()
        lgr.filters.clear()

    def _setup() -> None:
        setup_logging(logger_name="bench")

    results.append(
        bench(
            "setup_logging(logger_name='bench') [first-time]",
            _setup,
            iterations=2_000,
            repeats=5,
            before=_reset_setup_state,
        )
    )

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

    # RedactionFilter masking-overhead: patterns OFF (key-based only) vs the
    # curated DEFAULT_REDACTION_PATTERNS ON, over a representative free-text
    # message. Isolates the per-record regex hot-path cost of message/extra
    # scanning so the opt-in cost of pattern masking is documented (#445).
    from azure_functions_logging import DEFAULT_REDACTION_PATTERNS

    redaction_no_patterns = RedactionFilter()
    redaction_patterns = RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS)
    mask_msg = (
        "processing order o-42 for user u-1 in region koreacentral "
        "invocation 706b8e5c-a630-4309-b815-6410526f237a"
    )

    def _make_mask_record() -> logging.LogRecord:
        record = logging.LogRecord(
            name="bench",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=mask_msg,
            args=(),
            exc_info=None,
        )
        record.detail = mask_msg  # type: ignore[attr-defined]
        return record

    def _redaction_patterns_off() -> None:
        redaction_no_patterns.filter(_make_mask_record())

    def _redaction_patterns_on() -> None:
        redaction_patterns.filter(_make_mask_record())

    results.append(
        bench(
            "RedactionFilter.filter(record) [patterns off]",
            _redaction_patterns_off,
            iterations=50_000,
        )
    )
    results.append(
        bench(
            "RedactionFilter.filter(record) [DEFAULT_REDACTION_PATTERNS on]",
            _redaction_patterns_on,
            iterations=50_000,
        )
    )

    # ── End-to-end pipeline shapes (issue #714) ────────────────────────────
    # One controlled sequence per shape through the whole chain a caller pays
    # for: logger -> optional SamplingFilter -> JsonFormatter -> sink. Both
    # sinks are local (null and in-memory), so no I/O enters the measurement.
    # Redaction is deliberately excluded here: it is a safety path with its own
    # rows above, not part of the sampling/structured-logging overhead question.
    structured_extra = {
        "order_id": "o-42",
        "region": "koreacentral",
        "user": {"id": "u-1", "email": "a@b.com"},
    }
    null_sink = _NullSinkHandler()

    def _pipeline_logger(name: str, handler: logging.Handler, rate: int | None) -> logging.Logger:
        # A distinct logger per shape keeps the rows independent: reusing one
        # name would let a later configuration rewire an earlier row's handler.
        logger = logging.getLogger(f"bench.pipeline.{name}")
        logger.handlers.clear()
        logger.filters.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        if rate is not None:
            # One window long enough that only the first record can pass, so the
            # sampled row measures the drop path rather than the emit path.
            logger.addFilter(SamplingFilter(rate=rate, window=3_600.0))
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        return logger

    simple_logger = _pipeline_logger("simple", null_sink, rate=None)

    def _emit_simple() -> None:
        simple_logger.info("processing order %s", "o-42")

    results.append(
        bench("pipeline: simple -> null sink", _emit_simple, iterations=5_000, repeats=7)
    )

    structured_logger = _pipeline_logger("structured", null_sink, rate=None)

    def _emit_structured() -> None:
        structured_logger.info("processing order %s", "o-42", extra=structured_extra)

    results.append(
        bench("pipeline: structured -> null sink", _emit_structured, iterations=5_000, repeats=7)
    )

    memory_sink = _MemorySinkHandler()
    memory_logger = _pipeline_logger("memory", memory_sink, rate=None)

    def _emit_memory() -> None:
        memory_logger.info("processing order %s", "o-42", extra=structured_extra)

    def _clear_memory_sink() -> None:
        memory_sink.payloads.clear()

    results.append(
        bench(
            "pipeline: structured -> memory sink",
            _emit_memory,
            iterations=5_000,
            repeats=7,
            before=_clear_memory_sink,
        )
    )

    sampled_logger = _pipeline_logger("sampled", _NullSinkHandler(), rate=1)

    def _emit_sampled() -> None:
        sampled_logger.info("processing order %s", "o-42", extra=structured_extra)

    _emit_sampled()  # spend the one allowed slot untimed, so every timed call is dropped
    results.append(
        bench(
            "pipeline: structured, dropped by SamplingFilter",
            _emit_sampled,
            iterations=20_000,
            repeats=7,
        )
    )

    return results


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("azure-functions-logging")
    except Exception:  # noqa: BLE001 - metadata is absent in a bare source checkout
        return "unknown (not installed)"


def _git_revision() -> str:
    try:
        completed = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, no user input
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _environment() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "package": _package_version(),
        "revision": _git_revision(),
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
        f"  package {env['package']} @ {env['revision']}\n"
        f"  (in-process CPU cost per op; excludes gRPC / host / ingestion)\n"
    )
    print(f"{'benchmark':<50} {'median':>14} {'variability':>13} {'min':>14}")
    print("-" * 95)
    for r in results:
        print(r.as_row())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
