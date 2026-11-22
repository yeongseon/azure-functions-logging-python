"""Timing-harness contract for ``benchmarks/bench.py``.

Every pipeline row must share one timer around each batch so the printed
row-to-row deltas compare handler costs and not two different timing methods.
The per-call ``before`` hook stays available for the first-time
``setup_logging`` row, which resets state between calls by design.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

_BENCH_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "bench.py"


def _load_bench_module():
    spec = importlib.util.spec_from_file_location("bench_harness_under_test", _BENCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: the module defines dataclasses, and dataclasses
    # looks its own module up by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bench = _load_bench_module()


def test_reset_batch_runs_once_per_batch_not_per_iteration():
    calls: list[int] = []
    resets: list[int] = []

    result = bench.bench(
        "row",
        lambda: calls.append(1),
        iterations=5,
        repeats=3,
        reset_batch=lambda: resets.append(1),
    )

    assert len(calls) == 1 + 3 * 5  # warmup, then three batches of five calls
    assert len(resets) == 1 + 3  # once before the warmup, once per batch
    assert (result.iterations, result.repeats) == (5, 3)


def test_batched_row_takes_one_timer_per_batch(monkeypatch):
    ticks = 0
    real = bench.time.perf_counter_ns

    def counting() -> int:
        nonlocal ticks
        ticks += 1
        return real()

    monkeypatch.setattr(bench.time, "perf_counter_ns", counting)
    bench.bench("row", lambda: None, iterations=10, repeats=3, reset_batch=lambda: None)

    assert ticks == 2 * 3, "batched rows must not wrap every call in a timer"


def test_per_call_reset_keeps_its_own_timer(monkeypatch):
    ticks = 0
    real = bench.time.perf_counter_ns

    def counting() -> int:
        nonlocal ticks
        ticks += 1
        return real()

    monkeypatch.setattr(bench.time, "perf_counter_ns", counting)
    bench.bench("setup", lambda: None, iterations=4, repeats=2, before=lambda: None)

    assert ticks == 2 * 4 * 2, "the setup row still measures each call on its own"


def test_before_and_reset_batch_cannot_be_combined():
    with pytest.raises(ValueError, match="one timing method"):
        bench.bench(
            "row",
            lambda: None,
            iterations=1,
            repeats=1,
            before=lambda: None,
            reset_batch=lambda: None,
        )
