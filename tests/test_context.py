from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

import azure_functions_logging._context as ctx_mod
from azure_functions_logging._context import (
    ContextFilter,
    _check_cold_start,
    _extract_trace_id,
    cold_start_var,
    function_name_var,
    inject_context,
    invocation_id_var,
    logging_context,
    reset_context,
    restore_context,
    trace_id_var,
)


@pytest.fixture(autouse=True)
def reset_context_state() -> None:
    ctx_mod._cold_start = True
    invocation_id_var.set(None)
    function_name_var.set(None)
    trace_id_var.set(None)
    cold_start_var.set(None)


def test_context_filter_adds_default_none_values_to_record() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    keep = ContextFilter().filter(record)

    assert keep is True
    assert record.invocation_id is None  # type: ignore[attr-defined]
    assert record.function_name is None  # type: ignore[attr-defined]
    assert record.trace_id is None  # type: ignore[attr-defined]
    assert record.cold_start is None  # type: ignore[attr-defined]


def test_inject_context_sets_all_contextvars() -> None:
    context = SimpleNamespace(
        invocation_id="inv-1",
        function_name="fn-a",
        trace_context=SimpleNamespace(
            trace_parent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        ),
    )

    inject_context(context)

    assert invocation_id_var.get() == "inv-1"
    assert function_name_var.get() == "fn-a"
    assert trace_id_var.get() == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert cold_start_var.get() is True


def test_inject_context_with_mock_context_object() -> None:
    class TraceContext:
        trace_parent = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"

    class MockContext:
        invocation_id = "inv-mock"
        function_name = "mock-fn"
        trace_context = TraceContext()

    inject_context(MockContext())

    assert invocation_id_var.get() == "inv-mock"
    assert function_name_var.get() == "mock-fn"
    assert trace_id_var.get() == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_inject_context_missing_attributes_does_not_fail() -> None:
    class MissingContext:
        pass

    inject_context(MissingContext())

    assert invocation_id_var.get() is None
    assert function_name_var.get() is None
    assert trace_id_var.get() is None
    assert cold_start_var.get() is True


def test_inject_context_with_none_context() -> None:
    inject_context(None)

    assert invocation_id_var.get() is None
    assert function_name_var.get() is None
    assert trace_id_var.get() is None
    assert cold_start_var.get() is True


def test_extract_trace_id_valid_traceparent() -> None:
    trace_parent = "00-1234567890abcdef1234567890abcdef-fedcba0987654321-01"
    assert _extract_trace_id(trace_parent) == "1234567890abcdef1234567890abcdef"


@pytest.mark.parametrize("trace_parent", [None, "", "bad", "00-only"])
def test_extract_trace_id_invalid_or_empty(trace_parent: str | None) -> None:
    assert _extract_trace_id(trace_parent) is None


def test_cold_start_first_true_then_false() -> None:
    assert _check_cold_start() is True
    assert _check_cold_start() is False
    assert _check_cold_start() is False


def test_context_filter_reads_contextvars_after_inject_context() -> None:
    context = SimpleNamespace(
        invocation_id="inv-z",
        function_name="fn-z",
        trace_context=SimpleNamespace(
            trace_parent="00-ffffffffffffffffffffffffffffffff-1111111111111111-01"
        ),
    )
    inject_context(context)

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    ContextFilter().filter(record)

    assert record.invocation_id == "inv-z"  # type: ignore[attr-defined]
    assert record.function_name == "fn-z"  # type: ignore[attr-defined]
    assert record.trace_id == "ffffffffffffffffffffffffffffffff"  # type: ignore[attr-defined]
    assert record.cold_start is True  # type: ignore[attr-defined]


def test_inject_context_resets_vars_on_failure() -> None:
    """inject_context resets vars to None on attribute access failure
    to prevent context leak from a previous invocation.
    """
    # Pre-populate vars with stale values from a previous invocation
    invocation_id_var.set("stale-inv")
    function_name_var.set("stale-fn")
    trace_id_var.set("stale-trace")

    class BrokenContext:
        @property
        def invocation_id(self) -> str:
            raise RuntimeError("broken")

        @property
        def function_name(self) -> str:
            raise RuntimeError("broken")

        @property
        def trace_context(self) -> object:
            raise RuntimeError("broken")

    inject_context(BrokenContext())

    assert invocation_id_var.get() is None
    assert function_name_var.get() is None
    assert trace_id_var.get() is None


def test_reset_context_clears_all_contextvars() -> None:
    invocation_id_var.set("inv-x")
    function_name_var.set("fn-x")
    trace_id_var.set("trace-x")
    cold_start_var.set(True)

    reset_context()

    assert invocation_id_var.get() is None
    assert function_name_var.get() is None
    assert trace_id_var.get() is None
    assert cold_start_var.get() is None


def test_reset_context_is_idempotent() -> None:
    reset_context()
    reset_context()

    assert invocation_id_var.get() is None
    assert cold_start_var.get() is None


def test_logging_context_sets_then_resets() -> None:
    context = SimpleNamespace(
        invocation_id="inv-cm",
        function_name="fn-cm",
        trace_context=SimpleNamespace(
            trace_parent="00-cccccccccccccccccccccccccccccccc-2222222222222222-01"
        ),
    )

    with logging_context(context):
        assert invocation_id_var.get() == "inv-cm"
        assert function_name_var.get() == "fn-cm"
        assert trace_id_var.get() == "cccccccccccccccccccccccccccccccc"
        assert cold_start_var.get() is True

    assert invocation_id_var.get() is None
    assert function_name_var.get() is None
    assert trace_id_var.get() is None
    assert cold_start_var.get() is None


def test_logging_context_resets_even_when_body_raises() -> None:
    context = SimpleNamespace(invocation_id="inv-raise", function_name="fn-raise")

    with pytest.raises(RuntimeError, match="boom"):
        with logging_context(context):
            assert invocation_id_var.get() == "inv-raise"
            raise RuntimeError("boom")

    assert invocation_id_var.get() is None
    assert function_name_var.get() is None
    assert trace_id_var.get() is None
    assert cold_start_var.get() is None


def test_nested_logging_context_restores_outer() -> None:
    """Nested logging_context restores outer context on exit."""

    class OuterCtx:
        invocation_id = "outer-inv"
        function_name = "outer-fn"
        trace_context = SimpleNamespace(
            trace_parent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1-1111111111111111-01"
        )

    class InnerCtx:
        invocation_id = "inner-inv"
        function_name = "inner-fn"
        trace_context = SimpleNamespace(
            trace_parent="00-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2-2222222222222222-01"
        )

    with logging_context(OuterCtx()):
        assert invocation_id_var.get() == "outer-inv"
        assert function_name_var.get() == "outer-fn"
        assert trace_id_var.get() == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"
        assert cold_start_var.get() is True

        with logging_context(InnerCtx()):
            assert invocation_id_var.get() == "inner-inv"
            assert function_name_var.get() == "inner-fn"
            assert trace_id_var.get() == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2"
            assert cold_start_var.get() is False

        # After inner exits, outer is restored
        assert invocation_id_var.get() == "outer-inv"
        assert function_name_var.get() == "outer-fn"
        assert trace_id_var.get() == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"
        assert cold_start_var.get() is True

    # After outer exits, back to None
    assert invocation_id_var.get() is None
    assert function_name_var.get() is None
    assert trace_id_var.get() is None
    assert cold_start_var.get() is None


def test_inject_context_returns_tokens() -> None:
    """inject_context returns tokens that can be used with restore_context."""

    class Ctx:
        invocation_id = "tok-inv"
        function_name = "tok-fn"
        trace_context = None

    # Set initial state
    invocation_id_var.set("before")

    tokens = inject_context(Ctx())
    assert invocation_id_var.get() == "tok-inv"

    restore_context(tokens)
    assert invocation_id_var.get() == "before"

    # Cleanup
    invocation_id_var.set(None)


def test_restore_context_tokens_are_single_use() -> None:
    """Restoring the same tokens twice raises RuntimeError."""
    ctx = SimpleNamespace(invocation_id="x", function_name="f", trace_context=None)
    tokens = inject_context(ctx)
    restore_context(tokens)
    with pytest.raises(RuntimeError):
        restore_context(tokens)


def test_install_context_factory_injects_fields() -> None:
    """install_context_factory installs a LogRecordFactory that adds context fields."""
    from azure_functions_logging._context import install_context_factory

    # Reset factory state for test
    ctx_mod._factory_installed = False
    old_factory = logging.getLogRecordFactory()

    try:
        invocation_id_var.set("factory-inv")
        function_name_var.set("factory-fn")

        install_context_factory()

        factory = logging.getLogRecordFactory()
        record = factory(
            "test",
            logging.INFO,
            __file__,
            1,
            "hi",
            (),
            None,
        )
        assert record.invocation_id == "factory-inv"  # type: ignore[attr-defined]
        assert record.function_name == "factory-fn"  # type: ignore[attr-defined]

        # Idempotent
        install_context_factory()
    finally:
        logging.setLogRecordFactory(old_factory)
        ctx_mod._factory_installed = False
        invocation_id_var.set(None)
        function_name_var.set(None)
