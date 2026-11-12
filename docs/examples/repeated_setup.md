# Example: Repeated Setup Without Duplicates

A warm worker can run startup code more than once: a module is re-imported, or several
entry points each call `setup_logging()`. `examples/repeated_setup.py` shows what is
safe in standalone local mode with an explicit `logger_name`, and where its limits are.
It is offline and touches only its own logger namespace.

## Run it

```bash
pip install -e .
python examples/repeated_setup.py
```

The script calls setup three times (the last requests `DEBUG`), then logs. Output is
two JSON lines: `emitted once` from the configured logger and
`child emits once via inheritance` from a child logger. The `DEBUG` message is not
emitted.

## What repeated setup does

| Situation | Result |
| --- | --- |
| `setup_logging(logger_name=N)` called again | **No-op.** The first call for a name wins; one handler, one `ContextFilter`, each message emitted once. |
| The later call passes a different `level` or `format` | **Ignored.** Change the level afterwards with `logging.getLogger(N).setLevel(...)`; configure a different `logger_name` for a separate logger. |
| Root logger and other libraries | **Untouched** when you pass an explicit `logger_name`: their handlers, filters and levels are not modified. A named logger that receives a handler also stops propagating so an ancestor handler cannot print the record a second time. |
| A child logger such as `N.worker` | Emits **once through inheritance**: it owns no handler and reaches its parent's. |

Idempotency is per logger name; inheritance is how children reach that handler. They
are different mechanisms, so setting up both a parent and a child name installs two
handlers, and the child (which then no longer propagates) uses its own.

Azure / Core Tools mode (`FUNCTIONS_WORKER_RUNTIME` set) has a different contract: it is
idempotent per handler and *picks up handlers the host attached since the last call*,
without adding handlers or changing the root level. See the `setup_logging` reference.
This example does not exercise that mode.

## Teardown in tests

`teardown()` in the script removes the handler and filters from its own logger and
restores level and `propagate`. `setup_logging` remembers a configured name for the life
of the process, so after a teardown a second `configure()` is still a no-op: give each
test a unique `logger_name` (this repository's own tests clear the package's private
registry instead). `tests/test_examples.py` asserts this behavior.

## Verify locally

```bash
python -m pytest tests/test_examples.py -k TestRepeatedSetup --no-cov
```

The tests assert one handler and one `ContextFilter` after repeated calls, a single
emitted record, the ignored level change, unchanged root/library handlers, filters and
levels, and single emission from a child logger.

## Related

- [Troubleshooting: setup_logging has no effect](../troubleshooting.md#setup_logging-has-no-effect)
- [Logger Name Targeting](logger_name_targeting.md)
