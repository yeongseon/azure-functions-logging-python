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
from collections.abc import AsyncGenerator, AsyncIterator, Generator
import contextlib
import inspect
import logging
from types import SimpleNamespace
from typing import Any
import warnings

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

        result = asyncio.run(handler("req", _MOCK_CONTEXT))
        assert result == "ok"
        # Context reset after return
        assert invocation_id_var.get() is None


class TestGenerators:
    def test_sync_generator_injects_and_restores_context(self) -> None:
        @with_context
        def handler(context: object) -> Generator[str | None, None, None]:
            yield invocation_id_var.get()

        iterator = handler(_MOCK_CONTEXT)

        assert next(iterator) == "inv-dec"
        iterator.close()
        assert invocation_id_var.get() is None

    def test_sync_generators_restore_context_between_interleaved_resumes(self) -> None:
        @with_context
        def stream(context: object) -> Generator[str | None, None, None]:
            yield invocation_id_var.get()
            yield invocation_id_var.get()

        first = stream(SimpleNamespace(invocation_id="A"))
        second = stream(SimpleNamespace(invocation_id="B"))

        assert next(first) == "A"
        assert invocation_id_var.get() is None
        assert next(second) == "B"
        assert invocation_id_var.get() is None
        assert next(first) == "A"
        assert invocation_id_var.get() is None
        first.close()
        second.close()
        assert invocation_id_var.get() is None

    def test_sync_generator_preserves_return_value_with_context(self) -> None:
        """Regression (#584): a decorated sync generator's terminal return
        value must survive via StopIteration.value, just like the
        undecorated generator."""

        @with_context
        def stream(context: object) -> Generator[str, Any, dict[str, int]]:
            yield "item"
            return {"count": 1}

        iterator = stream(_MOCK_CONTEXT)
        assert next(iterator) == "item"
        with pytest.raises(StopIteration) as excinfo:
            next(iterator)
        assert excinfo.value.value == {"count": 1}

    def test_sync_generator_preserves_return_value_without_context(self) -> None:
        """Regression (#584): the no-context fallback path (`yield from`)
        must also forward the inner generator's return value -- it was
        previously discarded because the `yield from` expression's result
        was never captured and returned."""

        @with_context
        def stream(context: object) -> Generator[str, Any, dict[str, int]]:
            yield "item"
            return {"count": 1}

        iterator = stream(None)
        assert next(iterator) == "item"
        with pytest.raises(StopIteration) as excinfo:
            next(iterator)
        assert excinfo.value.value == {"count": 1}

    def test_sync_generator_return_value_reaches_yield_from_caller(self) -> None:
        """Regression (#584): the common `result = yield from decorated(...)`
        delegation pattern must receive the real return value, not None."""

        @with_context
        def stream(context: object) -> Generator[str, Any, dict[str, int]]:
            yield "item"
            return {"count": 1}

        def consume() -> Generator[str, Any, dict[str, int]]:
            result = yield from stream(_MOCK_CONTEXT)
            return result

        consumer = consume()
        assert next(consumer) == "item"
        with pytest.raises(StopIteration) as excinfo:
            next(consumer)
        assert excinfo.value.value == {"count": 1}

    def test_async_generator_injects_and_restores_context(self) -> None:
        @with_context
        async def handler(context: object) -> AsyncGenerator[str | None, None]:
            yield invocation_id_var.get()

        async def consume() -> str | None:
            iterator = handler(_MOCK_CONTEXT)
            value = await anext(iterator)
            await iterator.aclose()
            return value

        assert asyncio.run(consume()) == "inv-dec"
        assert invocation_id_var.get() is None

    def test_async_generator_closes_from_another_task(self) -> None:
        @with_context
        async def handler(context: object) -> AsyncGenerator[str | None, None]:
            yield invocation_id_var.get()

        async def consume() -> None:
            iterator = handler(_MOCK_CONTEXT)
            assert await asyncio.create_task(anext(iterator)) == "inv-dec"
            await asyncio.create_task(iterator.aclose())

        asyncio.run(consume())

    def test_async_generator_forwards_asend_with_context(self) -> None:
        """Regression (#585): asend(value) must reach the inner generator,
        not silently become a plain anext()."""

        @with_context
        async def handler(context: object) -> AsyncGenerator[Any, Any]:
            received = yield "ready"
            yield {"received": received}

        async def consume() -> list[Any]:
            iterator = handler(_MOCK_CONTEXT)
            first = await anext(iterator)
            second = await iterator.asend("payload")
            await iterator.aclose()
            return [first, second]

        assert asyncio.run(consume()) == ["ready", {"received": "payload"}]

    def test_async_generator_forwards_asend_without_context(self) -> None:
        """Regression (#585 acceptance): the no-context path must also
        forward asend, not just ordinary async-for iteration."""

        @with_context
        async def handler(context: object) -> AsyncGenerator[Any, Any]:
            received = yield "ready"
            yield {"received": received}

        async def consume() -> list[Any]:
            iterator = handler(None)
            first = await anext(iterator)
            second = await iterator.asend("payload")
            await iterator.aclose()
            return [first, second]

        assert asyncio.run(consume()) == ["ready", {"received": "payload"}]

    def test_async_generator_forwards_athrow_with_context(self) -> None:
        """Regression (#585): athrow(exc) must reach the user generator's
        own exception handling around its yield, preserving the recovery
        value it yields in response -- not let the exception escape
        unhandled."""

        @with_context
        async def handler(context: object) -> AsyncGenerator[Any, Any]:
            try:
                yield "ready"
            except ValueError as exc:
                yield {"caught": str(exc)}

        async def consume() -> Any:
            iterator = handler(_MOCK_CONTEXT)
            await anext(iterator)
            recovered = await iterator.athrow(ValueError("recoverable"))
            await iterator.aclose()
            return recovered

        assert asyncio.run(consume()) == {"caught": "recoverable"}

    def test_async_generator_forwards_unhandled_athrow(self) -> None:
        """Regression (#585): an unhandled athrow() must genuinely reach the
        inner generator's own frame before propagating -- not merely happen
        to surface at the wrapper's own un-caught yield, which would also
        look like 'propagation' without ever forwarding anything."""
        observed: list[str] = []

        @with_context
        async def handler(context: object) -> AsyncGenerator[Any, Any]:
            try:
                yield "ready"
            except ValueError:
                observed.append("inner-generator-received-it")
                raise

        async def consume() -> None:
            iterator = handler(_MOCK_CONTEXT)
            await anext(iterator)
            await iterator.athrow(ValueError("unhandled"))

        with pytest.raises(ValueError, match="unhandled"):
            asyncio.run(consume())
        assert observed == ["inner-generator-received-it"]

    def test_async_generator_used_as_asynccontextmanager_receives_exception(self) -> None:
        """Regression (#585 acceptance): a decorated async generator wrapped
        by contextlib.asynccontextmanager must receive an exception raised
        inside the `async with` block, matching undecorated behavior."""

        @contextlib.asynccontextmanager
        @with_context
        async def resource(context: object) -> AsyncIterator[str | None]:
            try:
                yield invocation_id_var.get()
            except ValueError as exc:
                raise RuntimeError(f"cleaned up after: {exc}") from exc

        async def consume() -> str:
            try:
                async with resource(_MOCK_CONTEXT) as value:
                    assert value == "inv-dec"
                    raise ValueError("boom")
            except RuntimeError as exc:
                return str(exc)
            return "no-exception-raised"

        assert asyncio.run(consume()) == "cleaned up after: boom"

    def test_async_handler_resets_on_exception(self) -> None:
        @with_context
        async def handler(req: object, context: object) -> str:
            raise ValueError("async boom")

        with pytest.raises(ValueError, match="async boom"):
            asyncio.run(handler("req", _MOCK_CONTEXT))

        assert invocation_id_var.get() is None

    def test_async_custom_param(self) -> None:
        @with_context(param="ctx")
        async def handler(req: object, ctx: object) -> str:
            assert function_name_var.get() == "fn-dec"
            return "ok"

        result = asyncio.run(handler("req", _MOCK_CONTEXT))
        assert result == "ok"


# ---------------------------------------------------------------------------
# 4. Context param not found → no crash (Principle 3)
# ---------------------------------------------------------------------------


class TestMissingContextParam:
    """When the handler cannot receive the expected context param, the decorator
    must not crash the app — it skips injection and warns (or raises when strict).
    """

    def test_no_context_param_warns_but_does_not_crash(self) -> None:
        with pytest.warns(RuntimeWarning, match="ineffective"):

            @with_context
            def handler(req: object) -> str:
                # No context injected — vars stay None
                assert invocation_id_var.get() is None
                return "ok"

        result = handler("req")
        assert result == "ok"

    def test_wrong_param_name_warns_but_does_not_crash(self) -> None:
        with pytest.warns(RuntimeWarning, match="'ctx'"):

            @with_context(param="ctx")
            def handler(req: object, context: object) -> str:
                # 'ctx' not in signature → no injection
                assert invocation_id_var.get() is None
                return "ok"

        result = handler("req", _MOCK_CONTEXT)
        assert result == "ok"

    def test_kwargs_signature_does_not_warn(self) -> None:
        # A **kwargs handler could receive the context by keyword at call time,
        # so the decorator must not warn about an ineffective injection.
        with warnings.catch_warnings():
            warnings.simplefilter("error")

            @with_context
            def handler(req: object, **kwargs: object) -> str:
                return "ok"

        assert handler("req") == "ok"

    def test_declared_context_param_does_not_warn(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")

            @with_context
            def handler(req: object, context: object) -> str:
                return "ok"

        assert handler("req", _MOCK_CONTEXT) == "ok"

    def test_strict_raises_on_missing_context_param(self) -> None:
        with pytest.raises(ValueError, match="ineffective"):

            @with_context(strict=True)
            def handler(req: object) -> str:  # pragma: no cover - never called
                return "ok"

    def test_strict_raises_on_kwargs_only_context_handler(self) -> None:
        with pytest.raises(ValueError, match="ineffective"):

            @with_context(strict=True)
            def handler(req: object, **kwargs: object) -> str:  # pragma: no cover
                return "ok"

    def test_strict_allows_declared_context_param(self) -> None:
        @with_context(strict=True)
        def handler(req: object, context: object) -> str:
            return "ok"

        assert handler("req", _MOCK_CONTEXT) == "ok"

    def test_async_missing_context_param_warns(self) -> None:
        with pytest.warns(RuntimeWarning, match="ineffective"):

            @with_context
            async def handler(req: object) -> str:
                assert invocation_id_var.get() is None
                return "ok"

        assert asyncio.run(handler("req")) == "ok"

    def test_async_strict_raises_on_missing_context_param(self) -> None:
        with pytest.raises(ValueError, match="ineffective"):

            @with_context(strict=True)
            async def handler(req: object) -> str:  # pragma: no cover
                return "ok"

    def test_uninspectable_signature_does_not_warn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Some callables have no introspectable signature; the decorator must be
        # conservative and never warn on a false positive when inspection fails.
        import inspect

        def _raise(_func: object) -> object:
            raise ValueError("no signature")

        monkeypatch.setattr(inspect, "signature", _raise)
        with warnings.catch_warnings():
            warnings.simplefilter("error")

            @with_context
            def handler(req: object) -> str:
                return "ok"

        assert handler("req") == "ok"


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


class TestGeneratorColdStart:
    """Regression (#586): a generator's cold_start must stay the same value
    across every resume of a SINGLE invocation -- the process-wide one-shot
    flag must be consumed exactly once per invocation, not once per resume.
    """

    def test_sync_generator_cold_start_stable_across_yields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from azure_functions_logging._context import ContextFilter

        caplog.handler.addFilter(ContextFilter())
        logger = logging.getLogger("test.cold-start.sync")

        @with_context
        def stream(context: object) -> Generator[int, Any, None]:
            logger.info("first")
            yield 1
            logger.info("second")
            yield 2
            logger.info("done")

        with caplog.at_level(logging.INFO):
            list(stream(_MOCK_CONTEXT))

        records = [r for r in caplog.records if r.name == logger.name]
        assert [r.getMessage() for r in records] == ["first", "second", "done"]
        assert [r.__dict__["cold_start"] for r in records] == [True, True, True]
        assert all(r.__dict__["invocation_id"] == "inv-dec" for r in records)

    def test_async_generator_cold_start_stable_across_yields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from azure_functions_logging._context import ContextFilter

        caplog.handler.addFilter(ContextFilter())
        logger = logging.getLogger("test.cold-start.async")

        @with_context
        async def stream(context: object) -> AsyncGenerator[int, None]:
            logger.info("first")
            yield 1
            logger.info("second")
            yield 2
            logger.info("done")

        async def consume() -> None:
            async for _ in stream(_MOCK_CONTEXT):
                pass

        with caplog.at_level(logging.INFO):
            asyncio.run(consume())

        records = [r for r in caplog.records if r.name == logger.name]
        assert [r.getMessage() for r in records] == ["first", "second", "done"]
        assert [r.__dict__["cold_start"] for r in records] == [True, True, True]

    def test_second_generator_invocation_is_not_cold_start(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from azure_functions_logging._context import ContextFilter

        caplog.handler.addFilter(ContextFilter())
        logger = logging.getLogger("test.cold-start.second-invocation")

        @with_context
        def stream(context: object) -> Generator[int, Any, None]:
            logger.info("first")
            yield 1
            logger.info("second")

        ctx2 = SimpleNamespace(
            invocation_id="inv-2",
            function_name="fn-2",
            trace_context=SimpleNamespace(trace_parent="00-bbbb-2222-01"),
        )
        with caplog.at_level(logging.INFO):
            list(stream(_MOCK_CONTEXT))  # first invocation -- consumes the global flag
            caplog.clear()
            list(stream(ctx2))  # second invocation -- must stay False throughout

        records = [r for r in caplog.records if r.name == logger.name]
        assert [r.getMessage() for r in records] == ["first", "second"]
        assert [r.__dict__["cold_start"] for r in records] == [False, False]

    def test_interleaved_sync_generators_each_keep_their_own_cold_start(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Regression (#586 acceptance): interleaved generator resumes must
        not cross-contaminate each other's cold-start value."""
        from azure_functions_logging._context import ContextFilter

        caplog.handler.addFilter(ContextFilter())
        logger = logging.getLogger("test.cold-start.interleaved")

        @with_context
        def stream(context: object) -> Generator[int, Any, None]:
            logger.info("a")
            yield 1
            logger.info("b")
            yield 2

        ctx2 = SimpleNamespace(
            invocation_id="inv-2",
            function_name="fn-2",
            trace_context=SimpleNamespace(trace_parent="00-bbbb-2222-01"),
        )
        with caplog.at_level(logging.INFO):
            first = stream(_MOCK_CONTEXT)  # first invocation created: True
            second = stream(ctx2)  # second invocation created: False
            next(first)
            next(second)
            next(first)
            next(second)

        records = [r for r in caplog.records if r.name == logger.name]
        by_invocation: dict[str, list[bool]] = {r.__dict__["invocation_id"]: [] for r in records}
        for r in records:
            by_invocation[r.__dict__["invocation_id"]].append(r.__dict__["cold_start"])
        assert by_invocation["inv-dec"] == [True, True]
        assert by_invocation["inv-2"] == [False, False]


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

    def test_lifecycle_default_off(self, caplog: pytest.LogCaptureFixture) -> None:
        # Pin the *declared default* so a future refactor cannot silently flip
        # an output-changing default (#425). Complements the behavioral check
        # above by asserting the signature default value itself, not just that
        # the bare-decorator path happens to emit nothing.
        assert inspect.signature(with_context).parameters["lifecycle"].default is False

        @with_context()
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

    def test_base_exception_propagates_without_error_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # KeyboardInterrupt/SystemExit and other BaseExceptions must propagate
        # unchanged and must NOT be logged as an "invocation error".
        @with_context(lifecycle=True)
        def handler(req: object, context: object) -> str:
            raise KeyboardInterrupt

        with caplog.at_level(logging.INFO):
            with pytest.raises(KeyboardInterrupt):
                handler("req", _MOCK_CONTEXT)

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        # Only the start record is emitted; no error record for BaseException.
        assert [r.message for r in events] == ["invocation start"]

    def test_async_cancelled_error_propagates_without_error_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @with_context(lifecycle=True)
        async def handler(req: object, context: object) -> str:
            raise asyncio.CancelledError

        with caplog.at_level(logging.INFO):
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(handler("req", _MOCK_CONTEXT))

        events = [r for r in caplog.records if hasattr(r, "lifecycle_event")]
        assert [r.message for r in events] == ["invocation start"]
