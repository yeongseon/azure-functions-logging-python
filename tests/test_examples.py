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

from azure_functions_logging import JsonFormatter
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
        "examples.repeated_setup",
        "examples.repeated_setup.worker",
        "examples.thirdparty_lib",
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


class TestRepeatedSetup:
    """Duplicate-handler and root-logger side-effect checks for examples/repeated_setup.py."""

    @pytest.fixture
    def module(self) -> Any:
        module = _load_example("repeated_setup")
        yield module
        module.teardown()

    @staticmethod
    def _json_handlers(logger: logging.Logger) -> list[logging.Handler]:
        return [h for h in logger.handlers if isinstance(h.formatter, JsonFormatter)]

    def test_main_runs_without_error(self, module: Any) -> None:
        module.main()

    def test_repeated_setup_installs_one_handler_and_emits_once(self, module: Any) -> None:
        logger = logging.getLogger(module.LOGGER_NAME)
        logger.handlers.clear()
        module.configure()
        module.configure()
        module.reconfigure_with_other_level()
        (handler,) = self._json_handlers(logger)
        # Exactly one stream handler of any kind (pytest's capture handlers are other types).
        assert [h for h in logger.handlers if type(h) is logging.StreamHandler] == [handler]
        stream = io.StringIO()
        handler.setStream(stream)  # type: ignore[attr-defined]
        logger.info("once")
        logger.debug("below the first call's level")
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert [r["message"] for r in rows] == ["once"]
        assert logger.level == logging.INFO  # the later DEBUG request was ignored
        assert logger.propagate is False
        assert len([f for f in handler.filters if type(f).__name__ == "ContextFilter"]) == 1

    def test_root_and_unrelated_library_handlers_are_untouched(self, module: Any) -> None:
        root = logging.getLogger()
        library = logging.getLogger("examples.thirdparty_lib")
        library_handler = logging.StreamHandler(io.StringIO())
        library.addHandler(library_handler)
        library.setLevel(logging.ERROR)
        before = (list(root.handlers), list(root.filters), root.level)
        library_before = (list(library.handlers), list(library_handler.filters), library.level)
        try:
            module.configure()
            module.configure()
            module.reconfigure_with_other_level()
            assert (list(root.handlers), list(root.filters), root.level) == before
            assert (
                list(library.handlers),
                list(library_handler.filters),
                library.level,
            ) == library_before
        finally:
            library.removeHandler(library_handler)

    def test_child_logger_emits_once_by_inheritance(self, module: Any) -> None:
        parent = logging.getLogger(module.LOGGER_NAME)
        parent.handlers.clear()
        module.configure()
        module.configure()
        (handler,) = self._json_handlers(parent)
        stream = io.StringIO()
        handler.setStream(stream)  # type: ignore[attr-defined]
        child = logging.getLogger(module.CHILD_NAME)
        assert self._json_handlers(child) == []  # inherits; owns no handler
        child.info("hello")
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert [r["logger"] for r in rows] == [module.CHILD_NAME]

    def test_teardown_leaves_the_idempotency_registry_so_tests_need_fresh_names(
        self, module: Any
    ) -> None:
        logger = logging.getLogger(module.LOGGER_NAME)
        logger.handlers.clear()
        module.configure()
        module.teardown()
        module.configure()  # still registered: a no-op, not a reinstall
        assert self._json_handlers(logger) == []


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
