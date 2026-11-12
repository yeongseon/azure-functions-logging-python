"""Smoke tests for examples/ scripts.

Each test imports and runs the example's ``main()`` function, verifying that
the public API works end-to-end without crashing. State is reset between tests
so ``setup_logging()`` idempotency and ``_cold_start`` toggling do not leak.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from azure_functions_logging import IsolatedHandler, JsonFormatter
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


class TestNoiseFilter:
    """Isolated-handler verification for examples/noise_filter.py."""

    @pytest.fixture
    def module(self) -> Any:
        return _load_example("noise_filter")

    @staticmethod
    def _seen(stream: io.StringIO) -> list[tuple[str, str, str]]:
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        return [(r["level"], r["logger"], r["message"]) for r in rows]

    def test_main_runs_without_error(self, module: Any) -> None:
        module.main()

    def test_noisy_info_is_sampled_while_warnings_errors_and_app_logs_pass(
        self, module: Any
    ) -> None:
        stream = io.StringIO()
        undo = module.install(stream)
        try:
            module.emit_traffic()
        finally:
            undo()
        noisy, app = module.THIRD_PARTY, module.APP
        assert self._seen(stream) == [
            ("INFO", noisy, "connection pool event 0"),
            ("INFO", noisy, "connection pool event 1"),
            ("WARNING", noisy, "retrying request"),
            ("ERROR", noisy, "request failed"),
            ("INFO", app, "order received"),
            ("INFO", app, "order validated"),
            ("INFO", app, "order completed"),
        ]

    def test_other_handlers_and_unrelated_loggers_are_left_intact(self, module: Any) -> None:
        root = logging.getLogger()
        root_before = (list(root.handlers), list(root.filters), root.level)
        scope = logging.getLogger(module.SCOPE)
        full, sampled = io.StringIO(), io.StringIO()
        sibling = logging.StreamHandler(full)
        sibling.setFormatter(JsonFormatter())
        scope.addHandler(sibling)
        unrelated_out = io.StringIO()
        unrelated = logging.getLogger("examples_noise_unrelated.lib")
        unrelated_handler = logging.StreamHandler(unrelated_out)
        unrelated.addHandler(unrelated_handler)
        unrelated.setLevel(logging.INFO)
        unrelated.propagate = False
        undo = module.install(sampled)
        try:
            module.emit_traffic()
            for index in range(5):
                unrelated.info("unrelated %d", index)
        finally:
            undo()
            scope.removeHandler(sibling)
            unrelated.removeHandler(unrelated_handler)

        assert len(self._seen(sampled)) == 7  # sampled on the isolated handler only
        assert len(self._seen(full)) == 10  # the sibling handler saw every record
        assert len(unrelated_out.getvalue().splitlines()) == 5
        assert sibling.filters == [] and unrelated_handler.filters == []
        assert (list(root.handlers), list(root.filters), root.level) == root_before

    def test_undo_removes_the_handler_and_restores_the_scope(self, module: Any) -> None:
        scope = logging.getLogger(module.SCOPE)
        scope.setLevel(logging.WARNING)  # distinct from what install() sets
        scope.propagate = True
        before = (list(scope.handlers), scope.level, scope.propagate)
        stream = io.StringIO()
        undo = module.install(stream)
        installed = [h for h in scope.handlers if h not in before[0]]
        assert len(installed) == 1
        isolated = installed[0]
        assert isinstance(isolated, IsolatedHandler)
        assert isolated.target.filters == []  # the wrapped target is not mutated
        undo()
        module.emit_traffic()
        assert stream.getvalue() == ""
        assert (list(scope.handlers), scope.level, scope.propagate) == before


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
