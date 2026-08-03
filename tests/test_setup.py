from __future__ import annotations

from collections.abc import Iterator
import logging
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from azure_functions_logging._context import ContextFilter
from azure_functions_logging._formatter import ColorFormatter
import azure_functions_logging._setup as setup_mod
from azure_functions_logging._setup import (
    _is_azure_hosted,
    _is_functions_environment,
    setup_logging,
)


@pytest.fixture(autouse=True)
def reset_setup_state() -> Iterator[None]:
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()
    saved_factory = logging.getLogRecordFactory()
    yield
    logging.setLogRecordFactory(saved_factory)
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()


def test_setup_logging_local_dev_adds_handler_with_color_formatter() -> None:
    logger_name = "afl.test.local"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, level=logging.DEBUG)

    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, ColorFormatter)

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_azure_env_adds_only_filter() -> None:
    root = logging.getLogger()
    root.filters.clear()
    test_handler = logging.StreamHandler()
    root.handlers = [test_handler]

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        setup_logging()

    assert root.handlers == [test_handler]
    assert any(isinstance(flt, ContextFilter) for flt in root.filters)
    assert any(isinstance(flt, ContextFilter) for flt in test_handler.filters)

    root.handlers = []
    root.filters.clear()


def test_setup_logging_is_idempotent() -> None:
    logger_name = "afl.test.idempotent"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name)
        first_handlers = list(logger.handlers)
        setup_logging(logger_name=logger_name)

    assert logger.handlers == first_handlers

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_is_idempotent_per_logger_name() -> None:
    first_name = "afl.test.idempotent.first"
    second_name = "afl.test.idempotent.second"
    first = logging.getLogger(first_name)
    second = logging.getLogger(second_name)
    first.handlers.clear()
    first.filters.clear()
    second.handlers.clear()
    second.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=first_name)
        setup_logging(logger_name=second_name)

    assert len(first.handlers) == 1
    assert len(second.handlers) == 1

    first.handlers.clear()
    first.filters.clear()
    second.handlers.clear()
    second.filters.clear()


def test_is_functions_environment() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert _is_functions_environment() is False
    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        assert _is_functions_environment() is True


def test_is_azure_hosted() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert _is_azure_hosted() is False
    with patch.dict(os.environ, {"WEBSITE_INSTANCE_ID": "abc123"}, clear=True):
        assert _is_azure_hosted() is True


def test_setup_logging_functions_formatter_applied_in_azure_env() -> None:
    root = logging.getLogger()
    root.filters.clear()
    test_handler = logging.StreamHandler()
    root.handlers = [test_handler]
    custom_formatter = logging.Formatter("%(message)s")

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        setup_logging(functions_formatter=custom_formatter)

    assert test_handler.formatter is custom_formatter

    root.handlers = []
    root.filters.clear()


def test_setup_logging_in_azure_env_does_not_install_duplicate_context_filters() -> None:
    root = logging.getLogger()
    root.handlers = [logging.StreamHandler()]
    root.filters.clear()

    import azure_functions_logging._setup as setup_mod

    setup_mod._configured_loggers.clear()

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        setup_logging()
        setup_logging()

    handler = root.handlers[0]
    context_filters_on_handler = [f for f in handler.filters if isinstance(f, ContextFilter)]
    context_filters_on_root = [f for f in root.filters if isinstance(f, ContextFilter)]

    assert len(context_filters_on_handler) == 1
    assert len(context_filters_on_root) == 1

    root.handlers = []
    root.filters.clear()


def test_is_functions_environment_with_only_website_instance_id_is_false() -> None:
    with patch.dict(os.environ, {"WEBSITE_INSTANCE_ID": "abc123"}, clear=True):
        assert _is_functions_environment() is False
        assert _is_azure_hosted() is True


def test_format_json_warns_in_azure_environment() -> None:
    """When format='json' and no functions_formatter in Azure, emit a warning."""
    import warnings

    root = logging.getLogger()
    root.handlers = [logging.StreamHandler()]

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging(format="json")

        assert len(w) == 1
        assert "format" in str(w[0].message).lower()
        assert "ignored" in str(w[0].message).lower()

    root.handlers = []
    root.filters.clear()


def test_format_color_no_warning_in_azure_environment() -> None:
    """When format='color' (default) in Azure, no warning."""
    import warnings

    root = logging.getLogger()
    root.handlers = [logging.StreamHandler()]

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging(format="color")

        assert len(w) == 0

    root.handlers = []
    root.filters.clear()


def test_setup_logging_warns_on_otel_formatter_conflict() -> None:
    """setup_logging() wires warn_otel_logging_misconfig (issue #256).

    With an OpenTelemetry handler attached and a functions_formatter passed,
    the '6a' ignored-formatter warning must surface through setup_logging().
    """
    import warnings

    class _FakeOtelHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
            pass

    _FakeOtelHandler.__module__ = "opentelemetry.sdk._logs._internal"

    root = logging.getLogger()
    root.handlers = [_FakeOtelHandler()]

    env = {
        "FUNCTIONS_WORKER_RUNTIME": "python",
        "PYTHON_ENABLE_OPENTELEMETRY": "1",
    }
    try:
        with patch.dict(os.environ, env, clear=True):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                setup_logging(functions_formatter=logging.Formatter())

            messages = [str(rec.message) for rec in w]
            assert any("functions_formatter" in m for m in messages)
    finally:
        root.handlers = []
        root.filters.clear()


def test_setup_logging_use_record_factory_installs_factory() -> None:
    """use_record_factory=True installs the global LogRecordFactory."""
    from azure_functions_logging._context import (
        _CONTEXT_FACTORY_MARKER,
    )

    logger_name = "afl.test.use_record_factory"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    baseline_factory = logging.getLogRecordFactory()
    assert not getattr(baseline_factory, _CONTEXT_FACTORY_MARKER, False)

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, use_record_factory=True)

    active_factory = logging.getLogRecordFactory()
    assert getattr(active_factory, _CONTEXT_FACTORY_MARKER, False) is True

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_use_record_factory_default_false_does_not_install() -> None:
    """Default behavior must not touch the global LogRecordFactory."""
    from azure_functions_logging._context import (
        _CONTEXT_FACTORY_MARKER,
    )

    logger_name = "afl.test.no_record_factory"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name)

    active_factory = logging.getLogRecordFactory()
    assert not getattr(active_factory, _CONTEXT_FACTORY_MARKER, False)

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_use_record_factory_is_idempotent() -> None:
    """Repeated setup_logging(use_record_factory=True) keeps a single factory."""
    from azure_functions_logging._context import (
        _CONTEXT_FACTORY_MARKER,
    )

    first_name = "afl.test.factory.first"
    second_name = "afl.test.factory.second"
    for name in (first_name, second_name):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=first_name, use_record_factory=True)
        first_factory = logging.getLogRecordFactory()
        setup_logging(logger_name=second_name, use_record_factory=True)
        second_factory = logging.getLogRecordFactory()

    assert first_factory is second_factory
    assert getattr(second_factory, _CONTEXT_FACTORY_MARKER, False) is True

    for name in (first_name, second_name):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.filters.clear()


def test_setup_logging_use_record_factory_skips_context_filter() -> None:
    """With use_record_factory=True, ContextFilter must NOT be attached.

    Otherwise the filter would overwrite factory-injected fields with current
    contextvar values at handler dispatch time, defeating the record-creation-
    time guarantee under queued / cross-thread / delayed handling.
    """
    logger_name = "afl.test.factory.no_filter"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, use_record_factory=True)

    assert not any(isinstance(f, ContextFilter) for f in logger.filters)
    for handler in logger.handlers:
        assert not any(isinstance(f, ContextFilter) for f in handler.filters)

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_factory_record_survives_contextvar_reset() -> None:
    """Regression: factory-injected fields must survive contextvar reset.

    Simulates queued/delayed handling: a record is created inside a context,
    then the context is reset before the handler runs. With use_record_factory,
    the snapshot must be preserved (no ContextFilter to overwrite it).
    """
    from azure_functions_logging._context import invocation_id_var

    logger_name = "afl.test.factory.snapshot"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, use_record_factory=True)

    token = invocation_id_var.set("test-invocation-123")
    try:
        record = logger.makeRecord(
            logger_name, logging.INFO, "f.py", 1, "msg", (), None,
        )
    finally:
        invocation_id_var.reset(token)

    # Context reset — but record was already created.
    invocation_id_var.set(None)

    # Run any handler filters (there should be none, but if any existed
    # they must not overwrite the snapshot).
    for handler in logger.handlers:
        for flt in handler.filters:
            if isinstance(flt, logging.Filter):
                flt.filter(record)

    assert getattr(record, "invocation_id", None) == "test-invocation-123"

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_invalid_format_leaves_no_global_side_effects() -> None:
    """Invalid `format` must raise BEFORE any global side effects (e.g. factory)."""
    baseline_factory = logging.getLogRecordFactory()

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="format must be"):
            setup_logging(format="bogus", use_record_factory=True)


    # Factory must not have been swapped despite use_record_factory=True
    assert logging.getLogRecordFactory() is baseline_factory


def test_azure_setup_picks_up_handlers_added_after_first_call() -> None:
    """Recovery: a handler added after setup_logging() must get the filter on the next call."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_filters = root.filters[:]

    try:
        env = {"FUNCTIONS_WORKER_RUNTIME": "python"}
        with patch.dict(os.environ, env, clear=True):
            # First call — root has no handlers yet
            root.handlers.clear()
            setup_logging()

            # Simulate host attaching a handler after the first call
            late_handler = logging.StreamHandler()
            root.addHandler(late_handler)

            # Second call — should pick up the late handler
            setup_logging()

        # The late handler must now carry the ContextFilter
        filter_types = [type(f).__name__ for f in late_handler.filters]
        assert "ContextFilter" in filter_types, (
            f"Expected ContextFilter on late handler, got: {filter_types}"
        )
    finally:
        root.handlers[:] = original_handlers
        root.filters[:] = original_filters


def test_azure_setup_does_not_duplicate_filter_on_repeated_calls() -> None:
    """Calling setup_logging() multiple times must not add duplicate filters."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_filters = root.filters[:]

    try:
        handler = logging.StreamHandler()
        root.addHandler(handler)

        env = {"FUNCTIONS_WORKER_RUNTIME": "python"}
        with patch.dict(os.environ, env, clear=True):
            setup_logging()
            setup_logging()
            setup_logging()

        context_filter_count = sum(
            1 for f in handler.filters if type(f).__name__ == "ContextFilter"
        )
        assert context_filter_count == 1, (", ".join(type(f).__name__ for f in handler.filters))
    finally:
        root.handlers[:] = original_handlers
        root.filters[:] = original_filters


def test_azure_setup_different_use_record_factory_flags_have_isolated_filter_state() -> None:
    """setup_logging(use_record_factory=True) must use separate state from
    setup_logging(use_record_factory=False) so the factory-snapshot guarantee
    is not undermined by reusing a ContextFilter created for a different mode."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_filters = root.filters[:]

    try:
        handler_no_factory = logging.StreamHandler()
        handler_with_factory = logging.StreamHandler()

        env = {"FUNCTIONS_WORKER_RUNTIME": "python"}
        with patch.dict(os.environ, env, clear=True):
            # Call with use_record_factory=False — should install ContextFilter
            root.handlers[:] = [handler_no_factory]
            setup_logging(use_record_factory=False)

            # Call with use_record_factory=True — must NOT install ContextFilter
            root.handlers[:] = [handler_with_factory]
            setup_logging(use_record_factory=True)

        filter_no_factory = next(
            (f for f in handler_no_factory.filters if type(f).__name__ == "ContextFilter"), None
        )
        filter_with_factory = next(
            (f for f in handler_with_factory.filters if type(f).__name__ == "ContextFilter"), None
        )

        assert filter_no_factory is not None, \
            "use_record_factory=False should install a ContextFilter on the handler"
        assert filter_with_factory is None, \
            "use_record_factory=True must not install a ContextFilter (factory provides context)"
        # The filter installed by the first call must not bleed onto the second handler
        assert filter_no_factory not in handler_with_factory.filters
    finally:
        root.handlers[:] = original_handlers
        root.filters[:] = original_filters


# ---------------------------------------------------------------------------
# PR 1 regression tests: remove ContextFilter when enabling record factory
# ---------------------------------------------------------------------------


def test_upgrade_to_record_factory_removes_existing_context_filter_local() -> None:
    """Regression: switching same logger from filter-mode to factory-mode removes stale filter.

    Scenario:
    1. setup_logging() installs ContextFilter on handler.
    2. setup_logging(use_record_factory=True) must strip that filter.
    3. Record created under context A, contextvar reset to B, handler filters run.
    4. Record must still carry context A (factory snapshot, not overwritten).
    """
    from azure_functions_logging._context import invocation_id_var

    logger_name = "afl.test.upgrade.local"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        # Step 1: install ContextFilter mode
        setup_logging(logger_name=logger_name)
        assert any(isinstance(f, ContextFilter) for h in logger.handlers for f in h.filters), \
            "precondition: ContextFilter should be on handler"

        # Step 2: upgrade to factory mode — must remove the filter
        setup_mod._configured_loggers.discard(logger_name)  # allow re-entry
        setup_logging(logger_name=logger_name, use_record_factory=True)

    # Assert filter is gone
    for handler in logger.handlers:
        assert not any(isinstance(f, ContextFilter) for f in handler.filters), \
            "ContextFilter must be removed after switching to use_record_factory=True"

    # Step 3: create record under context A
    token = invocation_id_var.set("context-A")
    try:
        record = logger.makeRecord(logger_name, logging.INFO, "f.py", 1, "msg", (), None)
    finally:
        invocation_id_var.reset(token)

    # Step 4: reset contextvar to a different value
    invocation_id_var.set("context-B")

    # Run handler filters (there should be none — assert snapshot is preserved)
    for handler in logger.handlers:
        for f in handler.filters:
            if hasattr(f, "filter"):
                f.filter(record)

    # Factory snapshot must survive
    assert getattr(record, "invocation_id", None) == "context-A", \
        f"Factory snapshot overwritten — got {getattr(record, 'invocation_id', None)!r}"

    logger.handlers.clear()
    logger.filters.clear()
    invocation_id_var.set(None)


def test_upgrade_to_record_factory_removes_context_filter_before_idempotency_guard() -> None:
    """Regression: cleanup must run even when logger_name is already in _configured_loggers.

    The early-return guard must NOT block filter removal.
    """
    logger_name = "afl.test.upgrade.idempotency"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    handler = logging.StreamHandler()
    cf = ContextFilter()
    handler.addFilter(cf)
    logger.addHandler(handler)

    # Simulate: logger was already configured in filter-mode
    setup_mod._configured_loggers.add(logger_name)

    with patch.dict(os.environ, {}, clear=True):
        # Even though logger_name is in _configured_loggers, cleanup must run
        setup_logging(logger_name=logger_name, use_record_factory=True)

    assert not any(isinstance(f, ContextFilter) for f in handler.filters), \
        "ContextFilter must be removed even when re-entering via idempotency guard"

    logger.handlers.clear()
    logger.filters.clear()


def test_upgrade_to_record_factory_removes_context_filter_azure_mode() -> None:
    """Regression: Azure mode — root handlers must have no ContextFilter after factory upgrade.

    When setup_logging(use_record_factory=False) is called first (adds ContextFilter),
    then setup_logging(use_record_factory=True) is called, the stale filter must be
    removed from all root handlers and root.filters.
    """
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_filters = root.filters[:]

    try:
        env = {"FUNCTIONS_WORKER_RUNTIME": "python"}
        test_handler = logging.StreamHandler()
        root.handlers[:] = [test_handler]
        root.filters.clear()

        with patch.dict(os.environ, env, clear=True):
            # First call — installs ContextFilter
            setup_logging(use_record_factory=False)
            assert any(isinstance(f, ContextFilter) for f in test_handler.filters), \
                "precondition: ContextFilter must be on handler after filter-mode call"

            # Second call — must remove ContextFilter
            setup_logging(use_record_factory=True)

        # After factory upgrade: no ContextFilter on handler or root logger
        assert not any(isinstance(f, ContextFilter) for f in test_handler.filters), \
            "ContextFilter must be removed from root handler after use_record_factory=True"
        assert not any(isinstance(f, ContextFilter) for f in root.filters), \
            "ContextFilter must be removed from root.filters after use_record_factory=True"
    finally:
        root.handlers[:] = original_handlers
        root.filters[:] = original_filters


class TestInjectionModeParity:
    """Guard: ContextFilter and LogRecordFactory modes enrich records with
    identical context fields, so neither mode implicitly relies on the other
    for coverage (design-review #210).
    """

    CONTEXT_FIELDS = ("invocation_id", "function_name", "trace_id", "cold_start")

    _TRACE_PARENT = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"

    class _Ctx:
        invocation_id = "inv-parity-1"
        function_name = "parity_fn"
        trace_context = SimpleNamespace(
            trace_parent="00-" + "a" * 32 + "-" + "b" * 16 + "-01"
        )

    # trace_id extracted from the W3C traceparent above.
    EXPECTED_TRACE_ID = "a" * 32

    def _fields(self, record: logging.LogRecord) -> dict[str, object]:
        return {f: getattr(record, f, "<<missing>>") for f in self.CONTEXT_FIELDS}

    def test_both_modes_enrich_identical_fields(self) -> None:
        from azure_functions_logging import inject_context, reset_context

        # --- ContextFilter mode ---
        reset_context()
        inject_context(self._Ctx())
        cf_record = logging.makeLogRecord({"msg": "m"})
        assert ContextFilter().filter(cf_record) is True
        filter_fields = self._fields(cf_record)
        reset_context()

        # --- LogRecordFactory mode ---
        logger_name = "afl.test.parity.factory"
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.filters.clear()
        with patch.dict(os.environ, {}, clear=True):
            setup_logging(logger_name=logger_name, use_record_factory=True)
        reset_context()
        inject_context(self._Ctx())
        factory_record = logger.makeRecord(
            logger_name, logging.INFO, "f.py", 1, "m", (), None,
        )
        factory_fields = self._fields(factory_record)
        reset_context()
        logger.handlers.clear()
        logger.filters.clear()

        # Every context field must be present (not the missing sentinel).
        assert "<<missing>>" not in filter_fields.values(), filter_fields
        assert "<<missing>>" not in factory_fields.values(), factory_fields
        # cold_start is a one-shot process-global, so compare the context-derived
        # fields for equality and assert cold_start is a bool in both modes.
        context_derived = ("invocation_id", "function_name", "trace_id")
        assert {k: filter_fields[k] for k in context_derived} == {
            k: factory_fields[k] for k in context_derived
        }, (
            "Injection modes diverged: "
            f"ContextFilter={filter_fields} LogRecordFactory={factory_fields}"
        )
        # Assert the extracted values match the injected context in BOTH modes,
        # so the parity check cannot pass by both modes failing identically
        # (e.g. all context-derived fields being None).
        expected = {
            "invocation_id": self._Ctx.invocation_id,
            "function_name": self._Ctx.function_name,
            "trace_id": self.EXPECTED_TRACE_ID,
        }
        assert {k: filter_fields[k] for k in context_derived} == expected, filter_fields
        assert {k: factory_fields[k] for k in context_derived} == expected, factory_fields
        assert isinstance(filter_fields["cold_start"], bool)
        assert isinstance(factory_fields["cold_start"], bool)
