"""Tests for the ``with_context`` decorator.

Covers:
- @with_context (no parens) with default ``context`` param name
- @with_context(param="ctx") with custom param name
- Async handler support
- Context reset in ``finally`` (context vars are None after handler returns)
- Context found in kwargs vs positional args
- Context param not found → no crash (Principle 3)
- Decorator preserves function metadata (functools.wraps)

Ref: https://github.com/yeongseon/azure-functions-logging/issues/22
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from azure_functions_logging import with_context
import azure_functions_logging._context as ctx_mod
from azure_functions_logging._context import (
    cold_start_var,
    function_name_var,
    invocation_id_var,
    trace_id_var,
)
import azure_functions_logging._setup as setup_mod


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Reset global state between tests."""
    setup_mod._configured_loggers.clear()
    ctx_mod._cold_start = True
    invocation_id_var.set(None)
    function_name_var.set(None)
    trace_id_var.set(None)
    cold_start_var.set(None)


_MOCK_CONTEXT = SimpleNamespace(
    invocation_id="inv-dec",
    function_name="fn-dec",
    trace_context=SimpleNamespace(
        trace_parent="00-aaaabbbbccccddddeeeeffffaaaabbbb-1111222233334444-01"
    ),
)


# ---------------------------------------------------------------------------
# 1. Sync: @with_context (no parentheses)
# ---------------------------------------------------------------------------


class TestSyncNoParens:
    """@with_context applied directly — default param name 'context'."""

    def test_injects_context_from_positional_arg(self) -> None:
        @with_context
        def handler(req: object, context: object) -> str:
            assert invocation_id_var.get() == "inv-dec"
            assert function_name_var.get() == "fn-dec"
            return "ok"

        result = handler("req", _MOCK_CONTEXT)
        assert result == "ok"

    def test_injects_context_from_kwarg(self) -> None:
        @with_context
        def handler(req: object, context: object) -> str:
            assert invocation_id_var.get() == "inv-dec"
            return "ok"

        result = handler("req", context=_MOCK_CONTEXT)
        assert result == "ok"

    def test_resets_context_vars_after_return(self) -> None:
        @with_context
        def handler(req: object, context: object) -> str:
            return "ok"

        handler("req", _MOCK_CONTEXT)
        assert invocation_id_var.get() is None
        assert function_name_var.get() is None
        assert trace_id_var.get() is None
        assert cold_start_var.get() is None

    def test_resets_context_vars_after_exception(self) -> None:
        @with_context
        def handler(req: object, context: object) -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            handler("req", _MOCK_CONTEXT)

        assert invocation_id_var.get() is None
        assert function_name_var.get() is None
        assert trace_id_var.get() is None
        assert cold_start_var.get() is None


# ---------------------------------------------------------------------------
# 2. Sync: @with_context(param="ctx")
# ---------------------------------------------------------------------------


class TestSyncCustomParam:
    """@with_context(param='ctx') — custom parameter name."""

    def test_injects_context_with_custom_param_name(self) -> None:
        @with_context(param="ctx")
        def handler(req: object, ctx: object) -> str:
            assert invocation_id_var.get() == "inv-dec"
            assert function_name_var.get() == "fn-dec"
            return "ok"

        result = handler("req", _MOCK_CONTEXT)
        assert result == "ok"

    def test_custom_param_kwarg(self) -> None:
        @with_context(param="ctx")
        def handler(req: object, ctx: object) -> str:
            assert invocation_id_var.get() == "inv-dec"
            return "ok"

        result = handler("req", ctx=_MOCK_CONTEXT)
        assert result == "ok"


# ---------------------------------------------------------------------------
# 3. Async handlers
# ---------------------------------------------------------------------------


class TestAsync:
    """with_context must support async handlers."""

    def test_async_handler_injects_and_resets(self) -> None:
        @with_context
        async def handler(req: object, context: object) -> str:
            assert invocation_id_var.get() == "inv-dec"
            return "ok"

        result = asyncio.get_event_loop().run_until_complete(handler("req", _MOCK_CONTEXT))
        assert result == "ok"
        # Context reset after return
        assert invocation_id_var.get() is None

    def test_async_handler_resets_on_exception(self) -> None:
        @with_context
        async def handler(req: object, context: object) -> str:
            raise ValueError("async boom")

        with pytest.raises(ValueError, match="async boom"):
            asyncio.get_event_loop().run_until_complete(handler("req", _MOCK_CONTEXT))

        assert invocation_id_var.get() is None

    def test_async_custom_param(self) -> None:
        @with_context(param="ctx")
        async def handler(req: object, ctx: object) -> str:
            assert function_name_var.get() == "fn-dec"
            return "ok"

        result = asyncio.get_event_loop().run_until_complete(handler("req", _MOCK_CONTEXT))
        assert result == "ok"


# ---------------------------------------------------------------------------
# 4. Context param not found → no crash (Principle 3)
# ---------------------------------------------------------------------------


class TestMissingContextParam:
    """When the handler doesn't have the expected context param,
    the decorator must not crash — just skip injection.
    """

    def test_no_context_param_does_not_crash(self) -> None:
        @with_context
        def handler(req: object) -> str:
            # No context injected — vars stay None
            assert invocation_id_var.get() is None
            return "ok"

        result = handler("req")
        assert result == "ok"

    def test_wrong_param_name_does_not_crash(self) -> None:
        @with_context(param="ctx")
        def handler(req: object, context: object) -> str:
            # 'ctx' not in signature → no injection
            assert invocation_id_var.get() is None
            return "ok"

        result = handler("req", _MOCK_CONTEXT)
        assert result == "ok"


# ---------------------------------------------------------------------------
# 4b. Positional-index resolution edge cases (PR #364 review)
# ---------------------------------------------------------------------------


class TestPositionalIndexEdgeCases:
    """The context arg must be resolved against positionally-passable params only.

    When the signature contains ``*args`` or keyword-only parameters, the
    decoration-time index must not point at a stray runtime positional slot.
    """

    def test_keyword_only_context_after_varargs_uses_kwarg(self) -> None:
        seen: dict[str, object] = {}

        @with_context
        def handler(req: object, *args: object, context: object) -> str:
            seen["inv"] = invocation_id_var.get()
            return "ok"

        # A naive full-parameter-list index would be 2 and, applied to the
        # positional args tuple ("req", "x", "y"), would grab "y" as the
        # context — injecting nothing and leaving invocation_id unset.
        result = handler("req", "x", "y", context=_MOCK_CONTEXT)
        assert result == "ok"
        assert seen["inv"] == "inv-dec"

    def test_keyword_only_context_injects_via_kwarg(self) -> None:
        @with_context
        def handler(req: object, *, context: object) -> str:
            assert invocation_id_var.get() == "inv-dec"
            return "ok"

        result = handler("req", context=_MOCK_CONTEXT)
        assert result == "ok"


# ---------------------------------------------------------------------------
# 5. Decorator preserves function metadata
# ---------------------------------------------------------------------------


class TestFunctools:
    """with_context must preserve __name__, __doc__, __module__ via functools.wraps."""

    def test_preserves_name_and_doc(self) -> None:
        @with_context
        def my_handler(req: object, context: object) -> str:
            """Handler docstring."""
            return "ok"

        assert my_handler.__name__ == "my_handler"
        assert my_handler.__doc__ == "Handler docstring."

    def test_preserves_name_with_parens(self) -> None:
        @with_context(param="context")
        def another_handler(req: object, context: object) -> str:
            """Another docstring."""
            return "ok"

        assert another_handler.__name__ == "another_handler"
        assert another_handler.__doc__ == "Another docstring."


# ---------------------------------------------------------------------------
# 6. Cold start detection through decorator
# ---------------------------------------------------------------------------


class TestColdStart:
    """The decorator must correctly propagate cold_start via inject_context."""

    def test_first_invocation_is_cold_start(self) -> None:
        @with_context
        def handler(req: object, context: object) -> bool | None:
            return cold_start_var.get()

        result = handler("req", _MOCK_CONTEXT)
        assert result is True

    def test_second_invocation_is_not_cold_start(self) -> None:
        @with_context
        def handler(req: object, context: object) -> bool | None:
            return cold_start_var.get()

        handler("req", _MOCK_CONTEXT)
        # Reset _cold_start is already False, but contextvars are reset by decorator
        # Need fresh context for second call
        ctx2 = SimpleNamespace(
            invocation_id="inv-2",
            function_name="fn-2",
            trace_context=SimpleNamespace(trace_parent="00-bbbb-2222-01"),
        )
        result = handler("req", ctx2)
        assert result is False


# ---------------------------------------------------------------------------
# 7. Shared worker-compat metadata helper
# ---------------------------------------------------------------------------


class TestCopyIdentityAttrs:
    """The shared ``copy_identity_attrs`` primitive must not leak state."""

    def test_copies_identity_without_wrapped_or_dict_alias(self) -> None:
        from azure_functions_logging._metadata_helpers import (
            SAFE_IDENTITY_ATTRS,
            copy_identity_attrs,
        )

        def func(req: object, context: object) -> None:
            """Original docstring."""

        def wrapper(*args: object, **kwargs: object) -> None:
            pass

        copy_identity_attrs(wrapper, func)

        for attr in SAFE_IDENTITY_ATTRS:
            assert getattr(wrapper, attr) == getattr(func, attr)
        # __wrapped__ must NOT be set (defeats worker indexing otherwise).
        assert not hasattr(wrapper, "__wrapped__")
        # __dict__ must not be aliased: mutating wrapper must not touch func.
        wrapper.__dict__["_marker"] = 1
        assert "_marker" not in func.__dict__


# ---------------------------------------------------------------------------
# 8. Opt-in invocation lifecycle logging (#382)
# ---------------------------------------------------------------------------


class TestLifecycleLogging:
    """@with_context(lifecycle=True) emits start/end/error records."""

    def test_disabled_by_default_emits_no_lifecycle_records(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @with_context
        def handler(req: object, context: object) -> str:
            return "ok"

        with caplog.at_level(logging.DEBUG):
            assert handler("req", _MOCK_CONTEXT) == "ok"

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert events == []

    def test_sync_success_emits_start_and_end(self, caplog: pytest.LogCaptureFixture) -> None:
        @with_context(lifecycle=True)
        def handler(req: object, context: object) -> str:
            return "ok"

        with caplog.at_level(logging.INFO):
            assert handler("req", _MOCK_CONTEXT) == "ok"

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert [r.message for r in events] == ["invocation start", "invocation end"]
        end = events[1]
        assert end.__dict__["outcome"] == "success"
        assert isinstance(end.__dict__["duration_ms"], float)
        assert end.__dict__["duration_ms"] >= 0.0

    def test_sync_exception_emits_error_and_reraises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @with_context(lifecycle=True)
        def handler(req: object, context: object) -> str:
            raise ValueError("boom")

        with caplog.at_level(logging.INFO):
            with pytest.raises(ValueError, match="boom"):
                handler("req", _MOCK_CONTEXT)

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert [r.message for r in events] == ["invocation start", "invocation error"]
        err = events[1]
        assert err.levelno == logging.ERROR
        assert err.__dict__["outcome"] == "error"
        assert err.exc_info is not None
        assert isinstance(err.__dict__["duration_ms"], float)

    def test_async_success_emits_start_and_end(self, caplog: pytest.LogCaptureFixture) -> None:
        @with_context(lifecycle=True)
        async def handler(req: object, context: object) -> str:
            return "ok"

        with caplog.at_level(logging.INFO):
            assert asyncio.run(handler("req", _MOCK_CONTEXT)) == "ok"

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert [r.message for r in events] == ["invocation start", "invocation end"]
        assert events[1].__dict__["outcome"] == "success"

    def test_async_exception_emits_error_and_reraises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @with_context(lifecycle=True)
        async def handler(req: object, context: object) -> str:
            raise ValueError("boom")

        with caplog.at_level(logging.INFO):
            with pytest.raises(ValueError, match="boom"):
                asyncio.run(handler("req", _MOCK_CONTEXT))

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert [r.message for r in events] == ["invocation start", "invocation error"]
        assert events[1].__dict__["outcome"] == "error"

    def test_configurable_level_suppresses_start_end_below_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @with_context(lifecycle=True, lifecycle_level=logging.DEBUG)
        def handler(req: object, context: object) -> str:
            return "ok"

        # Only capture INFO and above: DEBUG-level start/end are filtered out.
        with caplog.at_level(logging.INFO):
            assert handler("req", _MOCK_CONTEXT) == "ok"

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert events == []

    def test_lifecycle_records_carry_invocation_context(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from azure_functions_logging._context import ContextFilter

        # Attach the same filter setup_logging() uses so the capture handler
        # injects context fields, then assert the lifecycle records carry them.
        caplog.handler.addFilter(ContextFilter())

        @with_context(lifecycle=True)
        def handler(req: object, context: object) -> str:
            return "ok"

        with caplog.at_level(logging.INFO):
            handler("req", _MOCK_CONTEXT)

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert events, "expected lifecycle records"
        for record in events:
            assert record.__dict__["invocation_id"] == "inv-dec"
            assert record.__dict__["function_name"] == "fn-dec"
            assert record.__dict__["cold_start"] is True

    def test_lifecycle_without_context_still_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        @with_context(lifecycle=True)
        def handler(req: object) -> str:
            return "ok"

        with caplog.at_level(logging.INFO):
            assert handler("req") == "ok"

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert [r.message for r in events] == ["invocation start", "invocation end"]

    def test_async_lifecycle_without_context_still_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @with_context(lifecycle=True)
        async def handler(req: object) -> str:
            return "ok"

        with caplog.at_level(logging.INFO):
            assert asyncio.run(handler("req")) == "ok"

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert [r.message for r in events] == ["invocation start", "invocation end"]
