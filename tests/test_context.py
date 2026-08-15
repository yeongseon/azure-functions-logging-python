from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

import azure_functions_logging._context as ctx_mod
from azure_functions_logging._context import (
    _CONTEXT_FACTORY_MARKER,
    ContextFilter,
    TraceContextParts,
    _check_cold_start,
    _extract_trace_context,
    _install_context_factory,
    _uninstall_context_factory,
    cold_start_var,
    function_name_var,
    inject_context,
    invocation_id_var,
    logging_context,
    reset_context,
    restore_context,
    span_id_var,
    trace_id_var,
)


@pytest.fixture(autouse=True)
def reset_context_state() -> None:
    ctx_mod._cold_start = True
    invocation_id_var.set(None)
    function_name_var.set(None)
    trace_id_var.set(None)
    span_id_var.set(None)
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


def test_cold_start_first_true_then_false() -> None:
    assert _check_cold_start() is True
    assert _check_cold_start() is False
    assert _check_cold_start() is False


def test_cold_start_thread_safe_exactly_one_true() -> None:
    """Concurrent first calls: exactly one thread must observe cold_start=True."""
    import threading

    ctx_mod._cold_start = True  # reset for this test
    results: list[bool] = []
    barrier = threading.Barrier(10)

    def worker() -> None:
        barrier.wait()  # all threads start simultaneously
        results.append(_check_cold_start())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1, f"Expected exactly one True, got: {results}"
    assert results.count(False) == 9


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

    old_factory = logging.getLogRecordFactory()

    try:
        invocation_id_var.set("factory-inv")
        function_name_var.set("factory-fn")

        _install_context_factory()

        factory = logging.getLogRecordFactory()
        assert getattr(factory, _CONTEXT_FACTORY_MARKER, False) is True

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

        # Idempotent — calling again does not double-wrap
        _install_context_factory()
        assert logging.getLogRecordFactory() is factory
    finally:
        logging.setLogRecordFactory(old_factory)
        invocation_id_var.set(None)
        function_name_var.set(None)


def test_uninstall_context_factory_restores_previous() -> None:
    """uninstall_context_factory restores the factory active before install."""
    old_factory = logging.getLogRecordFactory()
    try:
        _install_context_factory()
        assert getattr(logging.getLogRecordFactory(), _CONTEXT_FACTORY_MARKER, False) is True

        assert _uninstall_context_factory() is True
        assert logging.getLogRecordFactory() is old_factory
        assert getattr(logging.getLogRecordFactory(), _CONTEXT_FACTORY_MARKER, False) is False
    finally:
        logging.setLogRecordFactory(old_factory)


def test_uninstall_context_factory_preserves_chained_factory() -> None:
    """Uninstall restores a custom factory that install had chained onto."""
    old_factory = logging.getLogRecordFactory()

    def custom_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.custom_field = "kept"
        return record

    try:
        logging.setLogRecordFactory(custom_factory)
        _install_context_factory()
        assert _uninstall_context_factory() is True
        assert logging.getLogRecordFactory() is custom_factory

        record = logging.getLogRecordFactory()("test", logging.INFO, __file__, 1, "msg", (), None)
        assert record.custom_field == "kept"  # type: ignore[attr-defined]
    finally:
        logging.setLogRecordFactory(old_factory)


def test_uninstall_context_factory_noop_when_not_installed() -> None:
    """uninstall_context_factory is a no-op when the factory is not active."""
    old_factory = logging.getLogRecordFactory()
    try:
        assert _uninstall_context_factory() is False
        assert logging.getLogRecordFactory() is old_factory
    finally:
        logging.setLogRecordFactory(old_factory)


def test_install_context_factory_chains_existing_factory() -> None:
    """Custom factory fields are preserved when context factory chains."""
    old_factory = logging.getLogRecordFactory()

    def custom_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.custom_field = "kept"
        return record

    try:
        logging.setLogRecordFactory(custom_factory)
        invocation_id_var.set("chain-inv")

        _install_context_factory()

        record = logging.getLogRecordFactory()("test", logging.INFO, __file__, 1, "msg", (), None)

        assert record.custom_field == "kept"  # type: ignore[attr-defined]
        assert record.invocation_id == "chain-inv"  # type: ignore[attr-defined]
    finally:
        logging.setLogRecordFactory(old_factory)
        invocation_id_var.set(None)


def test_install_context_factory_extra_collision_raises() -> None:
    """stdlib extra= with context field names raises KeyError when factory is active."""

    old_factory = logging.getLogRecordFactory()

    try:
        _install_context_factory()
        logger = logging.getLogger("test.factory.collision")
        logger.handlers.clear()
        logger.propagate = False
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        with pytest.raises(KeyError):
            logger.info("x", extra={"invocation_id": "manual"})
    finally:
        logging.setLogRecordFactory(old_factory)
        logger.handlers.clear()
        logger.propagate = True


def test_install_context_factory_with_logger_emit() -> None:
    """Context fields appear on records emitted through a real logger."""

    old_factory = logging.getLogRecordFactory()
    captured: list[logging.LogRecord] = []

    class CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    try:
        invocation_id_var.set("emit-inv")
        function_name_var.set("emit-fn")
        trace_id_var.set("emit-trace")
        cold_start_var.set(True)

        _install_context_factory()

        logger = logging.getLogger("test.factory.emit")
        logger.handlers.clear()
        logger.propagate = False
        logger.addHandler(CapturingHandler())
        logger.setLevel(logging.INFO)

        logger.info("hello from factory")

        assert len(captured) == 1
        rec = captured[0]
        assert rec.invocation_id == "emit-inv"  # type: ignore[attr-defined]
        assert rec.function_name == "emit-fn"  # type: ignore[attr-defined]
        assert rec.trace_id == "emit-trace"  # type: ignore[attr-defined]
        assert rec.cold_start is True  # type: ignore[attr-defined]
    finally:
        logging.setLogRecordFactory(old_factory)
        invocation_id_var.set(None)
        function_name_var.set(None)
        trace_id_var.set(None)
        cold_start_var.set(None)
        logger.handlers.clear()
        logger.propagate = True


# ---------------------------------------------------------------------------
# W3C traceparent strict validation (issue #104)
# ---------------------------------------------------------------------------

_VALID_TRACEPARENT = "00-1234567890abcdef1234567890abcdef-fedcba0987654321-01"
_VALID_TRACE_ID = "1234567890abcdef1234567890abcdef"


@pytest.mark.parametrize(
    "header",
    [
        # version 00 with extra trailing field
        "00-1234567890abcdef1234567890abcdef-fedcba0987654321-01-extra",
        # bad version length
        "0-1234567890abcdef1234567890abcdef-fedcba0987654321-01",
        "000-1234567890abcdef1234567890abcdef-fedcba0987654321-01",
        # reserved version ff
        "ff-1234567890abcdef1234567890abcdef-fedcba0987654321-01",
        # non-hex in version
        "zz-1234567890abcdef1234567890abcdef-fedcba0987654321-01",
        # short trace-id
        "00-1234567890abcdef1234567890abcde-fedcba0987654321-01",
        # long trace-id
        "00-1234567890abcdef1234567890abcdef0-fedcba0987654321-01",
        # non-hex trace-id
        "00-zzzz567890abcdef1234567890abcdef-fedcba0987654321-01",
        # all-zero trace-id
        "00-00000000000000000000000000000000-fedcba0987654321-01",
        # short span-id
        "00-1234567890abcdef1234567890abcdef-fedcba098765432-01",
        # long span-id
        "00-1234567890abcdef1234567890abcdef-fedcba09876543210-01",
        # all-zero span-id
        "00-1234567890abcdef1234567890abcdef-0000000000000000-01",
        # non-hex span-id
        "00-1234567890abcdef1234567890abcdef-zzzzzzzzzzzzzzzz-01",
        # bad flags length
        "00-1234567890abcdef1234567890abcdef-fedcba0987654321-1",
        "00-1234567890abcdef1234567890abcdef-fedcba0987654321-001",
        # non-hex flags
        "00-1234567890abcdef1234567890abcdef-fedcba0987654321-zz",
        # too few fields
        "00-1234567890abcdef1234567890abcdef-fedcba0987654321",
    ],
)
def test_extract_trace_context_rejects_malformed_headers(header: str) -> None:
    assert _extract_trace_context(header) is None


def test_extract_trace_context_returns_all_parts() -> None:
    parts = _extract_trace_context(_VALID_TRACEPARENT)
    assert parts == TraceContextParts(
        trace_id="1234567890abcdef1234567890abcdef",
        span_id="fedcba0987654321",
        trace_flags=1,
    )


def test_extract_trace_context_is_a_named_tuple() -> None:
    parts = _extract_trace_context(_VALID_TRACEPARENT)
    assert parts is not None
    assert parts.trace_id == _VALID_TRACE_ID
    assert parts.span_id == "fedcba0987654321"
    assert parts.trace_flags == 1


def test_extract_trace_context_normalizes_uppercase_hex_to_lowercase() -> None:
    # W3C mandates lowercase hex; OpenTelemetry's propagator rejects uppercase.
    # A lenient parser must still normalize to lowercase so JSON logs and OTel
    # emit identical trace/span ids (issue #278).
    upper = "00-1234567890ABCDEF1234567890ABCDEF-FEDCBA0987654321-0A"
    parts = _extract_trace_context(upper)
    assert parts == TraceContextParts(
        trace_id="1234567890abcdef1234567890abcdef",
        span_id="fedcba0987654321",
        trace_flags=0x0A,
    )


@pytest.mark.parametrize("trace_parent", [None, "", "bad", "00-only"])
def test_extract_trace_context_invalid_returns_none(trace_parent: str | None) -> None:
    assert _extract_trace_context(trace_parent) is None


def test_extract_trace_context_forward_compatible_future_version() -> None:
    future = "01-1234567890abcdef1234567890abcdef-fedcba0987654321-01-future"
    parts = _extract_trace_context(future)
    assert parts is not None
    assert parts.trace_id == _VALID_TRACE_ID
    assert parts.span_id == "fedcba0987654321"
    assert parts.trace_flags == 1


def test_context_filter_injects_extra_context_vars() -> None:
    import contextvars

    tenant_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
        "tenant_id", default=None
    )
    token = tenant_var.set("acme")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        keep = ContextFilter({"tenant_id": tenant_var}).filter(record)
        assert keep is True
        assert record.tenant_id == "acme"  # type: ignore[attr-defined]
        # Built-in fields still injected.
        assert record.invocation_id is None  # type: ignore[attr-defined]
    finally:
        tenant_var.reset(token)


def test_context_filter_extra_collision_raises() -> None:
    import contextvars

    bad_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
    with pytest.raises(ValueError, match="collide"):
        ContextFilter({"trace_id": bad_var})


def test_span_id_is_a_context_field() -> None:
    assert "span_id" in ContextFilter.CONTEXT_FIELDS


def test_inject_context_sets_span_id_from_traceparent() -> None:
    context = SimpleNamespace(
        invocation_id="inv-1",
        function_name="fn-a",
        trace_context=SimpleNamespace(
            trace_parent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        ),
    )
    inject_context(context)
    assert span_id_var.get() == "00f067aa0ba902b7"


def test_inject_context_span_id_none_when_no_traceparent() -> None:
    inject_context(SimpleNamespace())
    assert span_id_var.get() is None


def test_context_filter_adds_span_id_to_record() -> None:
    token = span_id_var.set("00f067aa0ba902b7")
    try:
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
        assert record.span_id == "00f067aa0ba902b7"  # type: ignore[attr-defined]
    finally:
        span_id_var.reset(token)


def test_context_factory_injects_span_id() -> None:
    assert "span_id" in ContextFilter.CONTEXT_FIELDS
    token = span_id_var.set("00f067aa0ba902b7")
    try:
        _install_context_factory()
        record = logging.getLogRecordFactory()("test", logging.INFO, __file__, 1, "hello", (), None)
        assert record.span_id == "00f067aa0ba902b7"  # type: ignore[attr-defined]
    finally:
        span_id_var.reset(token)
        _uninstall_context_factory()


def test_reset_context_clears_span_id() -> None:
    span_id_var.set("00f067aa0ba902b7")
    reset_context()
    assert span_id_var.get() is None
