# Example: Context Around Sync and Async Generators

`examples/generator_context.py` shows when invocation context is active while a
generator is suspended and resumed, and what is restored at each `yield`. It is a
local, offline script: the invocation ids are fake and no Azure Functions host is
needed.

## Run it

```bash
pip install -e .
python examples/generator_context.py
```

## What the demos show

| Demo | What you observe |
| --- | --- |
| `sync_demo()` | Records from the `@with_context` generator body carry `stream-invocation`; the consumer's own records, emitted between resumes, carry the caller's `outer-request`. The caller's context is restored at every `yield`. |
| `sync_demo(fail_after=2)` | The generator raises mid-stream. Afterwards the caller's records still carry `outer-request`, and a record after the `with` block carries no invocation id: nothing leaks. |
| `async_demo()` | The same contract for an `async` generator consumed with `async for`. |
| `scope_restoration_counterpart()` | A plain generator created inside `with logging_context(...)` but first advanced after the block runs with **no** invocation context, because context follows when the code *runs*, not where the generator was created. |

Expected shape (abridged to `invocation_id | message`):

```text
stream-invocation | producer yielding
outer-request     | consumer received
...
outer-request     | after iteration
None              | outside any context
None              | plain generator body runs
```

## Limits

- Context is carried by `contextvars` on the thread and task that resume the
  generator. It does **not** make arbitrary background threads inherit it; use
  [`propagate_context()`](../how-correlation-works.md#4-why-background-threads-lose-the-id)
  for work you hand to a thread.
- Decorate the generator function with `@with_context` (or open
  `logging_context()` inside the body around each section of work); a scope opened
  around the call that creates a plain generator does not cover later resumes.
- Use fake ids in examples and tests, as here; do not put real telemetry or secrets in
  fixtures.

## Verify locally

```bash
python -m pytest tests/test_examples.py -k TestGeneratorContext --no-cov
```

The tests capture the emitted JSON from a dedicated logger and assert the
`invocation_id` seen on each record for the sync, failing, async and plain-generator
cases, and that the context variable is cleared afterwards.

## Related Examples

- [Context Injection](context_injection.md)
- [How correlation works](../how-correlation-works.md)
