# Examples

`azure-functions-logging` includes standalone example scripts that demonstrate
every public API feature. Each script runs without Azure Functions installed.

| Role | Path | Description |
| --- | --- | --- |
| Representative | `examples/basic_setup.py` | One-liner `setup_logging()` + `get_logger()` with all log levels. |
| Focused | `examples/json_output.py` | JSON structured output via `setup_logging(format="json")`. |
| Focused | `examples/collision_safe_logging.py` | User fields that collide with `LogRecord` attributes: renamed, dropped or literal-wins, with metadata intact. |
| Focused | `examples/context_injection.py` | `logging_context()` with a mock `func.Context` for invocation metadata. |
| Focused | `examples/context_binding.py` | `logger.bind()` for per-request extra fields. |
| Focused | `examples/cold_start_detection.py` | Cold start toggle across consecutive `logging_context()` entries. |

Run any example directly:

```bash
pip install -e .
python examples/basic_setup.py
```
