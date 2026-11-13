# Example: Nested Context Binding and Request-Local Cleanup

A warm Azure Functions worker handles many invocations in one process, so scoped
context must not outlive its request. `examples/nested_context_binding.py` shows an
outer request scope with a stable correlation attribute, an inner scope that adds and
overrides fields, and proof that nothing carries into an unrelated request or task. It
is offline and uses fake ids and a plain `logging.Logger`.

## Run it

```bash
pip install -e .
python examples/nested_context_binding.py
```

## Outer and inner scopes

```python
with logging_context(ctx):                                  # invocation fields
    with bind_context(request_id="r-1", tenant="tenant-a", stage="request"):
        logger.info("request started")                      # stage=request
        with bind_context(item_id="item-1", stage="item"):
            logger.info("item processed")                   # adds item_id, stage=item
        logger.info("after inner scope")                    # item_id gone, stage=request
```

| Record | `invocation_id` | `extra` |
| --- | --- | --- |
| `request started` | `inv-r-1` | `request_id=r-1, tenant=tenant-a, stage=request` |
| `item processed` | `inv-r-1` | same plus `item_id=item-1`, `stage=item` (overridden) |
| `after inner scope` | `inv-r-1` | back to `stage=request`, no `item_id` |

`request_id` is the stable correlation attribute: it is present on every record of the
request, inner or outer. Exiting a `with` block restores the previous bindings, also
when the body raises.

## Nothing leaks into other requests

The script then handles a second request (`r-2`) in the same process, and two
interleaved asyncio tasks (`r-3`, `r-4`). Each record carries only its own request's
`invocation_id` and bindings, and after the requests a plain log record carries
neither. The tests assert this, together with the context variables being empty at the
end.

## `logger.bind()` versus scoped context

| | `get_logger(...).bind(k=v)` | `with bind_context(k=v):` |
| --- | --- | --- |
| Lifetime | Belongs to the returned **logger object**; follows it wherever it is used, until the object is dropped. | Belongs to the **scope**; ends when the `with` block exits. |
| Works with | `FunctionLogger` returned by `get_logger()` | any plain `logging.Logger` |
| Mutates the original logger | No (returns a new one) | No logger is changed; a `contextvars` binding is set and reset |
| Isolation | By object | Per asyncio task and per invocation; not inherited by new threads (use `propagate_context()`) |

`bind_versus_scope()` in the script shows one record inside a scope carrying both kinds
of field and one outside carrying only the logger-bound one. Neither mechanism changes
the logger's state machine or any logging defaults.

## Verify locally

```bash
python -m pytest tests/test_examples.py -k TestNestedContextBinding --no-cov
```

## Related Examples

- [Context Binding](context_binding.md)
- [Context Injection](context_injection.md)
- [How correlation works](../how-correlation-works.md)
