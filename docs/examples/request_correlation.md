# Example: Request Correlation Without Exposing Credentials

`examples/request_correlation.py` is a local, offline stand-in for an HTTP-triggered
handler. It emits structured request-correlation fields while keeping request
credentials out of the logs. It complements [Context Injection](context_injection.md)
(invocation metadata) and [Context Binding](context_binding.md) (per-request fields)
by adding the part those pages leave open: **what to take from a request**.

## Goal

Correlate every log line of one request (`invocation_id`, `function_name`, `trace_id`,
plus a caller-supplied `correlation_id`) without ever logging raw headers, access
tokens or API keys.

## Run it

```bash
pip install -e .
python examples/request_correlation.py
```

Each line is one JSON object. The request in the script carries synthetic
`Authorization` and `x-api-key` headers (`canary-*` values); neither appears in the
output, while the correlation fields do:

```json
{"level": "INFO", "message": "request received", "invocation_id": "11111111-2222-3333-4444-555555555555", "function_name": "OrdersHttp", "trace_id": "abcdef1234567890abcdef1234567890", "span_id": "1234567890abcdef", "extra": {"correlation_id": "order-7f3a", "method": "POST", "route": "orders"}}
```

(Fields such as `timestamp`, `cold_start` and `host_instance_id` are omitted above.)

## Logging boundaries

| Logged | Not logged |
| --- | --- |
| `method`, a fixed `route` name | `req.headers` as a whole, `Authorization`, `x-api-key`, cookies |
| `correlation_id` from `x-correlation-id`, **only** if it matches `[A-Za-z0-9._-]{1,64}` | A correlation header value that fails the check (for example a pasted token); the `invocation_id` is used instead |
| `invocation_id`, `function_name`, `trace_id` from `logging_context(context)` | The request body |

The pattern is an **allowlist**: bind the few fields you have decided are safe, rather
than logging everything and hoping redaction catches it. This example does not enable
redaction and makes no claim that arbitrary values are secret-safe. If you also opt in
to masking, see [secure production configuration](../configuration.md#secure-production-configuration);
it is a second line of defence, not a substitute for choosing fields.

## Verify locally

```bash
python -m pytest tests/test_examples.py -k TestRequestCorrelation --no-cov
```

The tests capture the emitted JSON from a dedicated logger (the root logger is not
modified) and assert that the correlation fields are present on every record, that
the synthetic credentials and the `headers` key never appear, and that an unsafe
`x-correlation-id` falls back to the invocation id. No Azure resources or credentials
are needed.

## Related Examples

- [Context Injection](context_injection.md)
- [Context Binding](context_binding.md)
- [How correlation works](../how-correlation-works.md)
