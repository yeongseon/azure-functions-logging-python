# Example: Collision-Safe Structured Logging

`examples/collision_safe_logging.py` shows what happens when user-supplied log fields
share a name with attributes the logging system already owns on a `LogRecord`
(`name`, `message`, `exc_info`, ...). It is a tiny offline script with fake values.

## Run it

```bash
pip install -e .
python examples/collision_safe_logging.py
```

The single JSON record keeps its own metadata and carries these extras:

```json
{"logger": "examples.collision_safe_logging", "message": "order accepted", "exception": null,
 "extra": {"extra_name": "user-supplied-name", "extra_message": "user-supplied-message",
           "a_b": 999, "order_id": 7}}
```

(Other fields such as `timestamp` and `host_instance_id` are omitted above.)

## Two mechanisms, two outcomes

Do not assume every collision is renamed.

| You pass | Collides with | Result |
| --- | --- | --- |
| `name="..."`, `message="..."` as extra fields of a `FunctionLogger` call | `LogRecord.name`, `LogRecord.message` (reserved keys) | **Renamed** to `extra_name`, `extra_message`; the value is still emitted and the record's own `logger`/`message` are untouched. |
| `exc={"info": "..."}` with `AttributeFlattenFilter(separator="_")` | the flattened key `exc_info` equals `LogRecord.exc_info` | **Dropped**: the generated key never overwrites an existing record attribute, so `exception` stays `null` and the value is not emitted under any name. |
| `a={"b": 1}` and a literal `a_b=999` | the flattened key `a_b` equals a literal extra key | The **literal key wins**; the generated one is dropped. |
| `order={"id": 7}` | nothing | Flattened to `order_id`. |

With the standard-library logger (not `get_logger()`), passing a reserved key in
`extra` raises `KeyError`; `FunctionLogger` is what renames it. The behavior is
described in the `AttributeFlattenFilter` docstring and exercised in
`tests/test_filters.py`; this example makes it runnable end to end.

## What this does not promise

It demonstrates metadata preservation only. It does not make arbitrary log data
secret-safe, does not change filter behavior, and prints no credentials; see
[secure production configuration](../configuration.md#secure-production-configuration)
for opt-in redaction.

## Verify locally

```bash
python -m pytest tests/test_examples.py -k TestCollisionSafeLogging --no-cov
```

The tests capture the emitted JSON and assert the record metadata, the renamed keys,
the dropped generated key, the literal-key precedence and that the example removes the
handler it installs.

## Related Examples

- [JSON Output](json_output.md)
- [Context Binding](context_binding.md)
