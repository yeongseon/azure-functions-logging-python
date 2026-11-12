# Examples

`azure-functions-logging` includes standalone example scripts that demonstrate
every public API feature. Each script runs without Azure Functions installed.

| Role | Path | Description |
| --- | --- | --- |
| Representative | `examples/basic_setup.py` | One-liner `setup_logging()` + `get_logger()` with all log levels. |
| Focused | `examples/json_output.py` | JSON structured output via `setup_logging(format="json")`. |
| Focused | `examples/context_injection.py` | `logging_context()` with a mock `func.Context` for invocation metadata. |
| Focused | `examples/context_binding.py` | `logger.bind()` for per-request extra fields. |
| Focused | `examples/secure_logging.py` | Opt-in `configure_secure_redaction()` with fake secrets: masked fields vs deliberately visible ones (not blanket detection). |
| Focused | `examples/cold_start_detection.py` | Cold start toggle across consecutive `logging_context()` entries. |

Run any example directly:

```bash
pip install -e .
python examples/basic_setup.py
```
