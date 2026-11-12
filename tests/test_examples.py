"""Smoke tests for examples/ scripts.

Each test imports and runs the example's ``main()`` function, verifying that
the public API works end-to-end without crashing. State is reset between tests
so ``setup_logging()`` idempotency and ``_cold_start`` toggling do not leak.
"""

from __future__ import annotations

from collections.abc import Iterator
from importlib.util import module_from_spec, spec_from_file_location
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from azure_functions_logging import configure_secure_redaction, get_logger, setup_logging
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
        "examples.secure_logging",
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


class TestSecureLogging:
    """Offline checks for examples/secure_logging.py (synthetic canaries only)."""

    @pytest.fixture(autouse=True)
    def _disable_secure_profile(self) -> Iterator[None]:
        yield
        configure_secure_redaction(enabled=False)

    def _fresh(self, module: Any) -> None:
        """Drop any handler already on the example logger so setup_logging installs its own."""
        logging.getLogger(module.LOGGER_NAME).handlers.clear()

    def _records(self, capsys: pytest.CaptureFixture[str]) -> tuple[list[dict[str, Any]], str]:
        raw = capsys.readouterr().err
        return [json.loads(line) for line in raw.splitlines()], raw

    def test_secure_preset_masks_sensitive_values_and_keeps_non_sensitive_fields(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _load_example("secure_logging")
        self._fresh(module)
        module.main()
        records, raw = self._records(capsys)
        for canary in (
            module.CANARY_A,
            module.CANARY_B,
            module.CANARY_C,
            module.CANARY_D,
        ):
            assert canary not in raw
        signed_in, accepted, upstream = records
        assert signed_in["extra"] == {"token": "***", "password": "***", "api_key": "***"}
        assert accepted["extra"] == {"order_id": "o-123", "tenant_id": "tenant-a", "status": "ok"}
        assert upstream["message"] == "calling upstream with password=***"

    def test_default_setup_without_the_preset_does_not_redact(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _load_example("secure_logging")
        self._fresh(module)
        setup_logging(format="json", logger_name=module.LOGGER_NAME)
        get_logger(module.LOGGER_NAME).info("plain", token=module.CANARY_A)
        _, raw = self._records(capsys)
        assert module.CANARY_A in raw

    def test_free_text_without_a_recognizable_key_is_not_promised_masked(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _load_example("secure_logging")
        self._fresh(module)
        module.main()
        capsys.readouterr()
        get_logger(module.LOGGER_NAME).info("note %s", "canary-free-text-0000")
        _, raw = self._records(capsys)
        assert "canary-free-text-0000" in raw


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
