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

Every row records its own `iterations` and `repeats`, the median across repeats,
the standard deviation across repeats, and the fastest repeat. `--json` also
carries the interpreter, platform, package version and git revision, so a run can
be compared with another one instead of trusting a single wall-clock number.

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

## Pipeline shapes: simple, structured, sampled

Four rows measure a whole record path — `logger.info()` → `makeRecord()` →
optional `SamplingFilter` → `JsonFormatter` → sink — instead of one component at
a time, over the three event shapes a Functions app actually emits:

| Row | Shape | What it isolates |
| --- | --- | --- |
| `pipeline: simple -> null sink` | `logger.info("processing order %s", "o-42")`, no extras | The unavoidable per-record cost: record creation, formatting, handler dispatch |
| `pipeline: structured -> null sink` | Same message plus `extra={order_id, region, user{id,email}}` | What carrying and serialising a structured payload adds |
| `pipeline: structured -> memory sink` | Same record, formatted output appended to a list | A handler that actually keeps the formatted line — still no I/O |
| `pipeline: structured, dropped by SamplingFilter` | Structured record on a logger with `SamplingFilter(rate=1, window=3600)` | What a **suppressed** record still costs — the saving sampling buys |

Both sinks are local: a null sink that formats and discards, and an in-memory
list sink. No socket, no file, no Azure. Redaction is deliberately **not** in the
pipeline rows: it is a safety path with its own rows above and must not be tuned
for speed.

Contributor run — CPython 3.14.10 (inside the supported `>=3.11,<3.15` range),
macOS 27.2.1 arm64, source checkout; 5,000 iterations × 7 repeats per emitted
row, 20,000 × 7 for the suppressed row:

| Row | Median | Variability (stdev across repeats) |
| --- | ---: | ---: |
| `pipeline: simple -> null sink` | ~9.6 µs | ±0.2 µs |
| `pipeline: structured -> null sink` | ~12.5 µs | ±0.2 µs |
| `pipeline: structured -> memory sink` | ~12.3 µs | ±0.4 µs |
| `pipeline: structured, dropped by SamplingFilter` | ~3.6 µs | ±0.1 µs |

All four rows share one timer around each batch; the memory sink is cleared
untimed between batches, so a row-to-row delta compares handler costs and not
two different timing methods.

Three consecutive runs on the same idle machine moved these medians by up to
~1.6 µs on the noisiest row, so treat the ordering and the ratio as the signal,
not the absolute microseconds. CPython 3.15 is outside the supported range and
is not used as a reference here.

Reading it: on this machine one emitted structured record costs ~12 µs of worker
CPU, while the same record costs ~3.6 µs when sampling drops it — sampling saves
roughly 70% of the per-record cost for chatty loggers, and the remaining third
is the record creation that happens before any filter runs. Absolute values are
machine-specific; the ratio is the stable part.

These rows are **not** part of `make test` or CI: `bench.py` stays a standalone,
opt-in script, so nothing here blocks a build.

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
| `RedactionFilter.filter(record)` **[patterns off]** | ~6.4 µs | Per record, key-based redaction only (message/extra *not* pattern-scanned); the opt-in-off baseline. |
| `RedactionFilter.filter(record)` **[`DEFAULT_REDACTION_PATTERNS` on]** | ~49 µs | Per record with free-text pattern masking enabled: ~7.6× the patterns-off cost. This is the hot-path regex price of the opt-in `patterns=` masking (#445) — enable it deliberately. |

_Environment: CPython 3.10.12, Linux x86_64. **Historical run** — CPython 3.10 predates this
package's supported range (`>=3.11,<3.15`). Treat the absolute numbers as an order-of-magnitude
reference and re-run the suite on a supported interpreter for anything load-bearing._

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
(and the environment line) to match your run. The table above predates the
pipeline rows; a fresh run prints all twelve rows.
