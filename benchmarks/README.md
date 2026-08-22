# Benchmarks

Minimal, reproducible micro-benchmarks for the hot paths `azure-functions-logging`
adds to your logging pipeline.

## Running

```bash
make bench                 # human-readable table (via hatch)
python benchmarks/bench.py # or run directly in any env with the package installed
python benchmarks/bench.py --json          # machine-readable output
python benchmarks/bench.py --include-import # also run the import-reload proxy
```

No pytest, no third-party benchmark framework, no network, no Azure — the script
uses only the stdlib plus this package's public API.

## What these numbers are (and are not)

These are **in-process CPU micro-benchmarks**. Each row is the median (across
repeats) of the per-operation cost on the machine that ran it, with GC disabled
during timing and a warmup pass.

They measure the cost this library adds **inside the Python worker process**:
context injection, JSON formatting, and the filters. They deliberately say
**nothing** about:

- gRPC transport from the worker to the host
- Application Insights ingestion, sampling, or schema mapping
- End-to-end latency of an HTTP invocation

Treat them as "is the per-record overhead in the microseconds or milliseconds
range?" evidence — not as a platform performance model. Re-run on your own
hardware for numbers that reflect your environment.

## Reference run

Captured on the maintainer's dev machine. **Your numbers will differ** — this
table exists to show order-of-magnitude, not to be a fixed contract.

| Benchmark | Median | Notes |
| --- | ---: | --- |
| `setup_logging(logger_name='bench')` **[first-time]** | ~10 µs | First-time configuration of one named logger (idempotency guard reset each iteration so this is *not* the re-entry fast-path). Paid once per process, not per-request. |
| `inject_context` + `restore_context` | ~6.7 µs | Lower-level path; per invocation |
| `logging_context(context)` enter/exit | ~8.3 µs | Recommended primary path; per invocation |
| `JsonFormatter.format(record)` | ~15 µs | Per emitted record, only when a record is actually formatted |
| `SamplingFilter.filter(record)` | ~0.8 µs | Per record on a filtered logger |
| `RedactionFilter.filter(record)` | ~11 µs | Per record (includes record construction); recursive over a nested payload |

_Environment: CPython 3.10.12, Linux x86_64._

### Reading the table

- **Per-invocation context cost** (`logging_context`) is a single-digit
  microsecond price paid once per request — negligible next to any I/O the
  handler does.
- **`JsonFormatter` / `RedactionFilter`** costs are paid **per emitted record**,
  and only for records that actually reach a handler using them. Chatty debug
  logging amplifies these; `SamplingFilter` (sub-microsecond) is the lever to
  pull when volume is the concern.
- **`setup_logging`** is a one-time startup cost, not a per-request cost.

To refresh this table, run `python benchmarks/bench.py` and update the numbers
(and the environment line) to match your run.
