"""Smoke tests for examples/ scripts.

Each test imports and runs the example's ``main()`` function, verifying that
the public API works end-to-end without crashing. State is reset between tests
so ``setup_logging()`` idempotency and ``_cold_start`` toggling do not leak.
"""

from __future__ import annotations

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from azure_functions_logging import setup_logging
import azure_functions_logging._context as ctx_mod
import azure_functions_logging._setup as setup_mod

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _load_example(name: str) -> Any:
    """Import an example script as a module and return it."""
    module_path = EXAMPLES_DIR / f"{name}.py"
    spec = spec_from_file_location(f"example_{name}", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load example from {module_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_logging_state() -> None:
    """Reset global state so each test starts fresh."""
    setup_mod._configured_loggers.clear()
    ctx_mod._cold_start = True

    # Clear handlers/filters added by previous tests on root + named loggers
    for logger_name in (
        None,
        "__main__",
        "example_basic_setup",
        "example_json_output",
        "example_context_injection",
        "example_context_binding",
        "example_cold_start_detection",
        "examples.nested_context_binding",
    ):
        lgr = logging.getLogger(logger_name)
        lgr.handlers.clear()
        lgr.filters.clear()


class TestBasicSetup:
    """Smoke test for examples/basic_setup.py."""

    def test_main_runs_without_error(self) -> None:
        module = _load_example("basic_setup")
        module.main()

    def test_logger_level_is_debug(self) -> None:
        module = _load_example("basic_setup")
        module.main()
        logger = logging.getLogger(module.__name__)
        assert logger.level <= logging.DEBUG


class TestJsonOutput:
    """Smoke test for examples/json_output.py."""

    def test_main_runs_without_error(self) -> None:
        module = _load_example("json_output")
        module.main()


class TestContextInjection:
    """Smoke test for examples/context_injection.py."""

    def test_main_runs_without_error(self) -> None:
        module = _load_example("context_injection")
        module.main()

    def test_fake_context_has_required_attributes(self) -> None:
        module = _load_example("context_injection")
        ctx = module._make_fake_context()
        assert hasattr(ctx, "invocation_id")
        assert hasattr(ctx, "function_name")
        assert hasattr(ctx.trace_context, "trace_parent")


class TestContextBinding:
    """Smoke test for examples/context_binding.py."""

    def test_main_runs_without_error(self) -> None:
        module = _load_example("context_binding")
        module.main()


class TestColdStartDetection:
    """Smoke test for examples/cold_start_detection.py."""

    def test_main_runs_without_error(self) -> None:
        module = _load_example("cold_start_detection")
        module.main()

    def test_cold_start_flips_after_first_entry(self) -> None:
        module = _load_example("cold_start_detection")
        # Before any injection, cold_start should be True
        assert ctx_mod._cold_start is True
        module.main()
        # After two logging_context entries, cold_start should be False
        assert ctx_mod._cold_start is False


class TestNestedContextBinding:
    """Request-local cleanup assertions for examples/nested_context_binding.py."""

    def _capture(self, module: Any) -> io.StringIO:
        stream = io.StringIO()
        target = logging.getLogger(module.LOGGER_NAME)
        target.handlers.clear()
        setup_logging(format="json", level=logging.INFO, logger_name=module.LOGGER_NAME)
        assert len(target.handlers) == 1
        target.handlers[0].setStream(stream)  # type: ignore[attr-defined]
        return stream

    @staticmethod
    def _rows(stream: io.StringIO) -> list[tuple[str, str | None, dict[str, Any]]]:
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        return [(r["message"], r["invocation_id"], r["extra"]) for r in records]

    def test_main_runs_without_error(self) -> None:
        module = _load_example("nested_context_binding")
        self._capture(module)
        module.main()

    def test_inner_scope_adds_and_overrides_then_restores_the_outer_values(self) -> None:
        module = _load_example("nested_context_binding")
        stream = self._capture(module)
        module.handle_request("r-1", "tenant-a")
        outer = {"request_id": "r-1", "tenant": "tenant-a", "stage": "request"}
        assert self._rows(stream) == [
            ("request started", "inv-r-1", outer),
            ("item processed", "inv-r-1", {**outer, "stage": "item", "item_id": "item-1"}),
            ("after inner scope", "inv-r-1", outer),
            ("request finished", "inv-r-1", outer),
        ]
        assert ctx_mod.invocation_id_var.get() is None
        assert ctx_mod.bound_context_var.get() == {}

    def test_values_do_not_carry_into_an_unrelated_sequential_request(self) -> None:
        module = _load_example("nested_context_binding")
        stream = self._capture(module)
        module.handle_request("r-1", "tenant-a")
        stream.truncate(0)
        stream.seek(0)
        module.handle_request("r-2", "tenant-b")
        for _, invocation_id, extra in self._rows(stream):
            assert invocation_id == "inv-r-2"
            assert extra["request_id"] == "r-2" and extra["tenant"] == "tenant-b"
        logging.getLogger(module.LOGGER_NAME).info("after both requests")
        assert self._rows(stream)[-1] == ("after both requests", None, {})

    def test_concurrent_tasks_keep_only_their_own_bindings(self) -> None:
        module = _load_example("nested_context_binding")
        stream = self._capture(module)
        asyncio.run(module.concurrent_requests())
        rows = self._rows(stream)
        assert len(rows) == 4
        for _, invocation_id, extra in rows:
            assert invocation_id == f"inv-{extra['request_id']}"
            assert extra["tenant"] == {"r-3": "tenant-c", "r-4": "tenant-d"}[extra["request_id"]]
        assert ctx_mod.bound_context_var.get() == {}

    def test_logger_bound_fields_follow_the_logger_scoped_fields_follow_the_scope(self) -> None:
        module = _load_example("nested_context_binding")
        stream = self._capture(module)
        module.bind_versus_scope()
        assert self._rows(stream) == [
            ("inside the scope", None, {"source": "logger-bound", "source_scope": "scope-bound"}),
            ("outside the scope", None, {"source": "logger-bound"}),
        ]


class TestOtelApp:
    """Structural guard for examples/otel_app (a deployable Function App).

    The app imports ``azure.functions`` and ``azure.monitor.opentelemetry``,
    which are not test dependencies, so it cannot be imported here. Instead we
    guard the wiring that the OpenTelemetry docs promise: the required call
    order and the PII/redaction attachment.
    """

    def _source(self) -> str:
        path = EXAMPLES_DIR / "otel_app" / "function_app.py"
        return path.read_text(encoding="utf-8")

    def test_app_files_exist(self) -> None:
        app_dir = EXAMPLES_DIR / "otel_app"
        assert (app_dir / "function_app.py").is_file()
        assert (app_dir / "host.json").is_file()
        assert (app_dir / "requirements.txt").is_file()

    def test_configure_azure_monitor_called_before_setup_logging(self) -> None:
        source = self._source()
        configure_at = source.index("configure_azure_monitor()")
        setup_at = source.index("setup_logging(")
        assert configure_at < setup_at, (
            "configure_azure_monitor() must run before setup_logging() so the "
            "OTel handler exists when filters are attached"
        )

    def test_app_enables_trace_activation_and_redaction(self) -> None:
        source = self._source()
        assert "activate_trace_context=True" in source
        assert "RedactionFilter()" in source
        assert ".addFilter(" in source

    def test_host_json_enables_opentelemetry_mode(self) -> None:
        import json as _json

        host = _json.loads((EXAMPLES_DIR / "otel_app" / "host.json").read_text(encoding="utf-8"))
        assert host["telemetryMode"] == "OpenTelemetry"

    def test_requirements_pin_otel_extra(self) -> None:
        reqs = (EXAMPLES_DIR / "otel_app" / "requirements.txt").read_text(encoding="utf-8")
        assert "azure-functions-logging[otel]" in reqs
        assert "azure-monitor-opentelemetry" in reqs
