"""Smoke tests for examples/ scripts.

Each test imports and runs the example's ``main()`` function, verifying that
the public API works end-to-end without crashing. State is reset between tests
so ``setup_logging()`` idempotency and ``_cold_start`` toggling do not leak.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import logging
from pathlib import Path
import re
from typing import Any

import pytest

from azure_functions_logging import (
    IsolatedHandler,
    JsonFormatter,
    configure_secure_redaction,
    get_logger,
    setup_logging,
)
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
        "examples.repeated_setup",
        "examples.repeated_setup.worker",
        "examples.thirdparty_lib",
        "examples.nested_context_binding",
        "examples.generator_context",
        "examples.secure_logging",
        "example_request_correlation",
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


class TestCollisionSafeLogging:
    """Metadata-preservation checks for examples/collision_safe_logging.py."""

    def _emit(self) -> tuple[dict[str, Any], str, Any]:
        module = _load_example("collision_safe_logging")
        stream = io.StringIO()
        module.emit(stream)
        raw = stream.getvalue()
        assert len(raw.splitlines()) == 1
        return json.loads(raw), raw, module

    def test_main_runs_without_error(self) -> None:
        _load_example("collision_safe_logging").main()

    def test_record_metadata_survives_every_collision(self) -> None:
        record, _, module = self._emit()
        assert record["logger"] == module.LOGGER_NAME
        assert record["message"] == "order accepted"
        assert record["level"] == "INFO"
        assert record["exception"] is None  # LogRecord.exc_info was not overwritten

    def test_reserved_extra_keys_are_renamed_not_dropped(self) -> None:
        record, _, _ = self._emit()
        assert record["extra"]["extra_name"] == "user-supplied-name"
        assert record["extra"]["extra_message"] == "user-supplied-message"

    def test_generated_flatten_key_colliding_with_metadata_is_dropped_not_renamed(self) -> None:
        record, raw, _ = self._emit()
        assert "user-supplied-detail" not in raw
        assert not any(key.startswith("extra_exc") for key in record["extra"])
        assert "exc_info" not in record["extra"]

    def test_literal_extra_key_wins_over_generated_one_and_others_flatten(self) -> None:
        record, _, _ = self._emit()
        assert record["extra"]["a_b"] == 999
        assert record["extra"]["order_id"] == 7
        assert set(record["extra"]) == {"extra_name", "extra_message", "a_b", "order_id"}

    def test_emit_leaves_the_example_logger_without_handlers(self) -> None:
        _, _, module = self._emit()
        # pytest may attach its own capture handlers to non-propagating loggers; only
        # the handler the example installed must be gone.
        leftover = [
            h
            for h in logging.getLogger(module.LOGGER_NAME).handlers
            if isinstance(h.formatter, JsonFormatter)
        ]
        assert leftover == []


class TestGeneratorContext:
    """Externally visible context assertions for examples/generator_context.py."""

    def _capture(self, module: Any) -> io.StringIO:
        stream = io.StringIO()
        target = logging.getLogger(module.LOGGER_NAME)
        target.handlers.clear()
        setup_logging(format="json", level=logging.INFO, logger_name=module.LOGGER_NAME)
        assert len(target.handlers) == 1
        target.handlers[0].setStream(stream)  # type: ignore[attr-defined]
        return stream

    @staticmethod
    def _seen(stream: io.StringIO) -> list[tuple[str | None, str]]:
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        return [(row["invocation_id"], row["message"]) for row in rows]

    def test_main_runs_without_error(self) -> None:
        module = _load_example("generator_context")
        self._capture(module)
        module.main()

    def test_sync_generator_runs_in_its_context_and_restores_the_callers(self) -> None:
        module = _load_example("generator_context")
        stream = self._capture(module)
        module.sync_demo()
        assert self._seen(stream) == [
            ("stream-invocation", "producer yielding"),
            ("outer-request", "consumer received"),
            ("stream-invocation", "producer yielding"),
            ("outer-request", "consumer received"),
            ("stream-invocation", "producer yielding"),
            ("outer-request", "consumer received"),
            ("outer-request", "after iteration"),
            (None, "outside any context"),
        ]
        assert ctx_mod.invocation_id_var.get() is None

    def test_context_is_cleaned_up_after_the_generator_raises(self) -> None:
        module = _load_example("generator_context")
        stream = self._capture(module)
        module.sync_demo(fail_after=2)
        assert self._seen(stream)[-4:] == [
            ("stream-invocation", "producer yielding"),
            ("outer-request", "consumer saw the failure"),
            ("outer-request", "after iteration"),
            (None, "outside any context"),
        ]
        assert ctx_mod.invocation_id_var.get() is None

    def test_async_generator_has_the_same_contract(self) -> None:
        module = _load_example("generator_context")
        stream = self._capture(module)
        asyncio.run(module.async_demo())
        assert self._seen(stream) == [
            ("stream-invocation", "async producer yielding"),
            ("outer-request", "async consumer received"),
            ("stream-invocation", "async producer yielding"),
            ("outer-request", "async consumer received"),
            ("outer-request", "after async iteration"),
            (None, "outside any context"),
        ]
        assert ctx_mod.invocation_id_var.get() is None

    def test_plain_generator_is_not_bound_to_its_creation_scope(self) -> None:
        module = _load_example("generator_context")
        stream = self._capture(module)
        module.scope_restoration_counterpart()
        assert self._seen(stream) == [(None, "plain generator body runs")]


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
        assert upstream["message"] == "calling upstream with api_key=***"

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


class TestRequestCorrelation:
    """Offline checks for examples/request_correlation.py (synthetic canaries only)."""

    CANARIES = ("canary-bearer-token-0000", "canary-api-key-0000")

    def _run(self, module: Any, headers: dict[str, str]) -> tuple[list[dict[str, Any]], str]:
        stream = io.StringIO()
        # Dedicated logger: setup_logging attaches the context filter and JSON
        # formatter here, and the root logger is left untouched.
        target = logging.getLogger(module.__name__)
        target.handlers.clear()
        setup_logging(format="json", level=logging.INFO, logger_name=module.__name__)
        assert len(target.handlers) == 1
        target.handlers[0].setStream(stream)  # type: ignore[attr-defined]
        status = module.handle_request(
            module._make_fake_request(headers), module._make_fake_context()
        )
        assert status == 200
        raw = stream.getvalue()
        return [json.loads(line) for line in raw.splitlines()], raw

    def test_main_runs_without_error(self) -> None:
        _load_example("request_correlation").main()

    def test_records_carry_invocation_and_request_correlation(self) -> None:
        module = _load_example("request_correlation")
        records, _ = self._run(module, {"x-correlation-id": "order-7f3a"})
        assert [r["message"] for r in records] == ["request received", "request completed"]
        for record in records:
            assert record["invocation_id"] == "11111111-2222-3333-4444-555555555555"
            assert record["function_name"] == "OrdersHttp"
            assert record["trace_id"] == "abcdef1234567890abcdef1234567890"
            assert record["extra"]["correlation_id"] == "order-7f3a"
            assert record["extra"]["method"] == "POST"

    def test_credentials_and_raw_headers_never_reach_the_output(self) -> None:
        module = _load_example("request_correlation")
        headers = {
            "x-correlation-id": "order-7f3a",
            "Authorization": f"Bearer {self.CANARIES[0]}",
            "x-api-key": self.CANARIES[1],
        }
        records, raw = self._run(module, headers)
        for canary in self.CANARIES:
            assert canary not in raw
        for record in records:
            assert "headers" not in record["extra"]
            assert "Authorization" not in raw

    def test_unsafe_correlation_header_falls_back_to_invocation_id(self) -> None:
        module = _load_example("request_correlation")
        pasted = f"Bearer {self.CANARIES[0]}"
        records, raw = self._run(module, {"x-correlation-id": pasted})
        assert self.CANARIES[0] not in raw
        assert {r["extra"]["correlation_id"] for r in records} == {
            "11111111-2222-3333-4444-555555555555"
        }


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
