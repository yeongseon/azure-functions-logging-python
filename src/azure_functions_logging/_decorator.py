"""Decorator helper for automatic context injection.

Provides ``with_context`` — a decorator that calls ``inject_context()``
before the handler runs and restores previous context variables after it completes.

Ref: https://github.com/yeongseon/azure-functions-logging-python/issues/22
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Callable, TypeVar, overload

from ._context import logging_context
from ._metadata import LoggingMetadata, read_logging_metadata, set_logging_metadata
from ._metadata_helpers import copy_identity_attrs

_F = TypeVar("_F", bound=Callable[..., Any])

_DEFAULT_PARAM = "context"


def _copy_safe_metadata(wrapper: Callable[..., Any], func: Callable[..., Any]) -> None:
    """Copy safe metadata from ``func`` onto ``wrapper`` without setting ``__wrapped__``.

    Unlike :func:`functools.wraps`, this helper deliberately:

    * does NOT set ``__wrapped__`` — the Azure Functions worker may follow
      it during function indexing and bind the original (un-wrapped)
      handler instead of ours, defeating context injection;
    * does NOT copy ``__dict__`` — sharing the dict object aliases
      wrapper.__dict__ with func.__dict__, causing later setattr calls
      (e.g. _azure_functions_metadata) to leak onto the original ``func``.

    It still mirrors ``__signature__`` and ``__annotations__`` so the worker
    can introspect parameter names/types for trigger binding.
    """
    copy_identity_attrs(wrapper, func)
    try:
        wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
    except (TypeError, ValueError):  # pragma: no cover
        pass
    wrapper.__annotations__ = dict(getattr(func, "__annotations__", {}) or {})


def _build_logging_payload(param: str) -> LoggingMetadata:
    """Construct the typed ``logging`` namespace payload."""
    return {"version": 1, "context_param": param}


def _resolve_positional_index(func: Callable[..., Any], param: str) -> int | None:
    """Resolve the positional index of *param* once, at decoration time.

    Returns the parameter's index **among positionally-passable parameters**
    (``POSITIONAL_ONLY`` / ``POSITIONAL_OR_KEYWORD``) so the index lines up with
    the runtime positional ``args`` tuple. Returns ``None`` when the signature
    cannot be introspected, or when *param* is keyword-only or a ``*args`` /
    ``**kwargs`` parameter (which can never be matched positionally). Computing
    this once avoids calling ``inspect.signature`` on every invocation.
    """
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return None
    positional_kinds = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    index = 0
    for name, parameter in parameters.items():
        if parameter.kind not in positional_kinds:
            continue
        if name == param:
            return index
        index += 1
    return None


def _find_context_arg(
    param: str,
    positional_index: int | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Locate the context argument by keyword name or precomputed position."""
    # Check kwargs first
    if param in kwargs:
        return kwargs[param]

    # Fall back to positional args using the index resolved at decoration time.
    if positional_index is not None and positional_index < len(args):
        return args[positional_index]

    return None


def _lifecycle_logger_for(func: Callable[..., Any]) -> logging.Logger:
    """Resolve the logger used for lifecycle records, once at decoration time."""
    return logging.getLogger(
        getattr(func, "__module__", None) or "azure_functions_logging.lifecycle"
    )


def _log_lifecycle_start(logger: logging.Logger, level: int) -> None:
    if logger.isEnabledFor(level):
        logger.log(level, "invocation start", extra={"lifecycle_event": "start"})


def _log_lifecycle_end(
    logger: logging.Logger,
    level: int,
    start_time: float,
    outcome: str,
    exc: BaseException | None,
) -> None:
    if outcome == "error":
        emit_level = logging.ERROR
    elif logger.isEnabledFor(level):
        emit_level = level
    else:
        # Success record below the effective level: skip before doing any work.
        return
    duration_ms = round((time.perf_counter() - start_time) * 1000, 3)
    logger.log(
        emit_level,
        "invocation error" if outcome == "error" else "invocation end",
        exc_info=exc if outcome == "error" else None,
        extra={
            "lifecycle_event": "end",
            "outcome": outcome,
            "duration_ms": duration_ms,
        },
    )


def _run_with_lifecycle_sync(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    logger: logging.Logger,
    level: int,
) -> Any:
    start_time = time.perf_counter()
    _log_lifecycle_start(logger, level)
    try:
        result = func(*args, **kwargs)
    except BaseException as exc:
        _log_lifecycle_end(logger, level, start_time, "error", exc)
        raise
    _log_lifecycle_end(logger, level, start_time, "success", None)
    return result


async def _run_with_lifecycle_async(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    logger: logging.Logger,
    level: int,
) -> Any:
    start_time = time.perf_counter()
    _log_lifecycle_start(logger, level)
    try:
        result = await func(*args, **kwargs)
    except BaseException as exc:
        _log_lifecycle_end(logger, level, start_time, "error", exc)
        raise
    _log_lifecycle_end(logger, level, start_time, "success", None)
    return result


def _wrap_sync(
    func: _F,
    param: str,
    activate_trace_context: bool | None,
    lifecycle: bool,
    lifecycle_level: int,
) -> _F:
    """Wrap a synchronous handler."""
    context_index = _resolve_positional_index(func, param)
    lifecycle_logger = _lifecycle_logger_for(func) if lifecycle else None

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = _find_context_arg(param, context_index, args, kwargs)

        def _invoke() -> Any:
            if lifecycle_logger is not None:
                return _run_with_lifecycle_sync(
                    func, args, kwargs, lifecycle_logger, lifecycle_level
                )
            return func(*args, **kwargs)

        if ctx is not None:
            with logging_context(ctx, activate_trace_context=activate_trace_context):
                return _invoke()
        return _invoke()

    _copy_safe_metadata(wrapper, func)
    set_logging_metadata(wrapper, func, _build_logging_payload(param))
    return wrapper  # type: ignore[return-value]


def _wrap_async(
    func: _F,
    param: str,
    activate_trace_context: bool | None,
    lifecycle: bool,
    lifecycle_level: int,
) -> _F:
    """Wrap an asynchronous handler."""
    context_index = _resolve_positional_index(func, param)
    lifecycle_logger = _lifecycle_logger_for(func) if lifecycle else None

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = _find_context_arg(param, context_index, args, kwargs)

        async def _invoke() -> Any:
            if lifecycle_logger is not None:
                return await _run_with_lifecycle_async(
                    func, args, kwargs, lifecycle_logger, lifecycle_level
                )
            return await func(*args, **kwargs)

        if ctx is not None:
            with logging_context(ctx, activate_trace_context=activate_trace_context):
                return await _invoke()
        return await _invoke()

    _copy_safe_metadata(wrapper, func)
    set_logging_metadata(wrapper, func, _build_logging_payload(param))
    return wrapper  # type: ignore[return-value]


@overload
def with_context(func: _F) -> _F: ...


@overload
def with_context(
    *,
    param: str = ...,
    activate_trace_context: bool | None = ...,
    lifecycle: bool = ...,
    lifecycle_level: int = ...,
) -> Callable[[_F], _F]: ...


def with_context(
    func: _F | None = None,
    *,
    param: str = _DEFAULT_PARAM,
    activate_trace_context: bool | None = None,
    lifecycle: bool = False,
    lifecycle_level: int = logging.INFO,
) -> _F | Callable[[_F], _F]:
    """Decorator that automatically injects invocation context.

    Can be used with or without arguments::

        @with_context
        def handler(req, context):
            ...

        @with_context(param="ctx")
        def handler(req, ctx):
            ...

    The decorator:

    1. Finds the ``context`` parameter (by name, default ``"context"``)
    2. Calls ``inject_context(context)`` before the handler body
    3. Restores the previous context in ``finally`` after the handler returns

    Both sync and async handlers are supported.

    Args:
        func: The handler function (when used without parentheses).
        param: Name of the parameter that receives the Azure Functions
            context object. Defaults to ``"context"``.
        activate_trace_context: When ``True``, also attach the host's W3C trace
            context so OTel log records inherit the host span's
            ``trace_id``/``span_id`` (requires the ``[otel]`` extra; silent
            no-op otherwise). When ``None`` (default), the process-wide default
            configured via ``setup_logging(activate_trace_context=...)`` applies.
        lifecycle: When ``True``, emit opt-in invocation lifecycle records — a
            ``"invocation start"`` record before the handler runs and an
            ``"invocation end"`` record after it returns (or ``"invocation
            error"`` if it raises). End/error records carry ``duration_ms`` and
            ``outcome`` extras. Exceptions are logged then re-raised unchanged.
            Defaults to ``False`` (no output, zero overhead when disabled).
        lifecycle_level: Log level for the start/end lifecycle records when
            ``lifecycle=True``. Defaults to ``logging.INFO``. Error records are
            always emitted at ``logging.ERROR``.
    """

    def decorator(fn: _F) -> _F:
        if asyncio.iscoroutinefunction(fn):
            return _wrap_async(fn, param, activate_trace_context, lifecycle, lifecycle_level)
        return _wrap_sync(fn, param, activate_trace_context, lifecycle, lifecycle_level)

    if func is not None:
        # Called as @with_context (no parentheses)
        return decorator(func)

    # Called as @with_context(...) (with parentheses)
    return decorator


def get_logging_metadata(func: Any) -> dict[str, Any] | None:
    """Return logging metadata if the function was decorated with ``with_context``.

    Returns ``None`` if the function has no logging metadata attached.
    """
    meta = read_logging_metadata(func)
    return dict(meta) if meta is not None else None
