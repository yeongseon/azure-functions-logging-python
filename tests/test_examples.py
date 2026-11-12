"""Smoke tests for examples/ scripts.

Each test imports and runs the example's ``main()`` function, verifying that
the public API works end-to-end without crashing. State is reset between tests
so ``setup_logging()`` idempotency and ``_cold_start`` toggling do not leak.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import logging
from pathlib import Path
import re
from typing import Any

import pytest

import azure_functions_logging._context as ctx_mod
import azure_functions_logging._setup as setup_mod

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _load_example(name: str) -> Any:
    """Import an example script as a module and return it."""
    module_path = EXAMPLES_DIR / f"{name}.py"
    spec = spec_from_file_location(f"example_{name.replace('/', '_')}", module_path)
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

    def test_app_runs_offline_with_in_memory_exporter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Run the real handler with a stubbed exporter: correlation and redaction hold.

        ``azure.monitor.opentelemetry`` is replaced by an in-memory OTel pipeline, so
        this proves the app's wiring order, trace activation and redaction, and
        nothing about delivery to Azure Monitor.
        """
        pytest.importorskip("opentelemetry.sdk._logs")
        import sys
        import types

        import azure.functions as func
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor

        exporter = InMemoryLogExporter()  # type: ignore[no-untyped-call]
        provider = LoggerProvider()
        provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
        calls: list[str] = []
        root = logging.getLogger()
        original_level = root.level

        def configure_azure_monitor(**_: Any) -> None:
            calls.append("configure_azure_monitor")
            root.addHandler(LoggingHandler(level=logging.INFO, logger_provider=provider))

        stub = types.ModuleType("azure.monitor.opentelemetry")
        stub.configure_azure_monitor = configure_azure_monitor  # type: ignore[attr-defined]
        for name in ("azure.monitor", "azure.monitor.opentelemetry"):
            monkeypatch.delitem(sys.modules, name, raising=False)
        monkeypatch.setitem(sys.modules, "azure.monitor", types.ModuleType("azure.monitor"))
        monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", stub)
        try:
            module = _load_example("otel_app/function_app")
            handler_fn = module.process_order._function.get_user_function()
            trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
            context = types.SimpleNamespace(
                invocation_id="inv-otel-1",
                function_name="process_order",
                trace_context=types.SimpleNamespace(
                    trace_parent=f"00-{trace_id}-00f067aa0ba902b7-01"
                ),
            )
            request = func.HttpRequest(
                method="GET",
                url="/api/orders",
                params={"order_id": "o-42"},
                body=b"",
            )
            response = handler_fn(request, context)
        finally:
            for handler in list(root.handlers):
                if isinstance(handler, LoggingHandler):
                    root.removeHandler(handler)
            root.setLevel(original_level)
            provider.shutdown()

        assert calls == ["configure_azure_monitor"]
        assert response.status_code == 200
        emitted = [r.log_record for r in exporter.get_finished_logs()]
        assert [r.body for r in emitted][0] == "Request received"
        assert len(emitted) == 4
        for record in emitted:
            assert format(record.trace_id, "032x") == trace_id
            assert dict(record.attributes or {})["order_id"] == "o-42"
        processing = emitted[2]
        assert dict(processing.attributes or {})["password"] != "should-be-masked"

    def test_readme_otel_walkthrough_matches_the_app(self) -> None:
        """Every path and requirement the README names for otel_app must exist."""
        readme = (EXAMPLES_DIR / "README.md").read_text(encoding="utf-8")
        start = readme.index("## OpenTelemetry app")
        section = readme[start:]
        for rel in set(re.findall(r"examples/[A-Za-z0-9_./-]+\.(?:py|json|txt)\b", section)):
            assert (EXAMPLES_DIR.parent / rel).is_file(), f"README names a missing file: {rel}"
        command = re.search(r"^func start --script-root (\S+)$", section, re.M)
        assert command is not None
        assert (EXAMPLES_DIR.parent / command.group(1) / "function_app.py").is_file()
        requirements = (EXAMPLES_DIR / "otel_app" / "requirements.txt").read_text(encoding="utf-8")
        for package in ("azure-functions-logging[otel]", "azure-monitor-opentelemetry"):
            assert package in section
            assert package in requirements
        assert "tests/test_examples.py -k TestOtelApp" in section
        assert "does **not** prove" in section

    def test_host_json_enables_opentelemetry_mode(self) -> None:
        import json as _json

        host = _json.loads((EXAMPLES_DIR / "otel_app" / "host.json").read_text(encoding="utf-8"))
        assert host["telemetryMode"] == "OpenTelemetry"

    def test_requirements_pin_otel_extra(self) -> None:
        reqs = (EXAMPLES_DIR / "otel_app" / "requirements.txt").read_text(encoding="utf-8")
        assert "azure-functions-logging[otel]" in reqs
        assert "azure-monitor-opentelemetry" in reqs
