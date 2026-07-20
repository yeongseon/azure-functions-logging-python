"""Decorator helper for automatic context injection.

Provides ``with_context`` — a decorator that calls ``inject_context()``
before the handler runs and restores previous context variables after it completes.

Ref: https://github.com/yeongseon/azure-functions-logging/issues/22
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, TypeVar, overload

from ._context import inject_context, restore_context
from ._metadata import LoggingMetadata, read_logging_metadata, set_logging_metadata

_F = TypeVar("_F", bound=Callable[..., Any])

_DEFAULT_PARAM = "context"




_SAFE_COPY_ATTRS = ("__name__", "__qualname__", "__doc__", "__module__")


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
    for attr in _SAFE_COPY_ATTRS:
        try:
            object.__setattr__(wrapper, attr, getattr(func, attr))
        except (AttributeError, TypeError):  # pragma: no cover
            pass
    try:
        wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
    except (TypeError, ValueError):  # pragma: no cover
        pass
    wrapper.__annotations__ = dict(getattr(func, "__annotations__", {}) or {})


def _build_logging_payload(param: str) -> LoggingMetadata:
    """Construct the typed ``logging`` namespace payload."""
    return {"version": 1, "context_param": param}



def _find_context_arg(
    func: Callable[..., Any],
    param: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Locate the context argument by parameter name."""
    # Check kwargs first
    if param in kwargs:
        return kwargs[param]

    # Fall back to positional args
    try:
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        idx = params.index(param)
        if idx < len(args):
            return args[idx]
    except (ValueError, IndexError):
        pass

    return None


def _wrap_sync(func: _F, param: str) -> _F:
    """Wrap a synchronous handler."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = _find_context_arg(func, param, args, kwargs)
        if ctx is not None:
            tokens = inject_context(ctx)
        else:
            tokens = {}
        try:
            return func(*args, **kwargs)
        finally:
            restore_context(tokens)

    _copy_safe_metadata(wrapper, func)
    set_logging_metadata(wrapper, func, _build_logging_payload(param))
    return wrapper  # type: ignore[return-value]


def _wrap_async(func: _F, param: str) -> _F:
    """Wrap an asynchronous handler."""

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = _find_context_arg(func, param, args, kwargs)
        if ctx is not None:
            tokens = inject_context(ctx)
        else:
            tokens = {}
        try:
            return await func(*args, **kwargs)
        finally:
            restore_context(tokens)

    _copy_safe_metadata(wrapper, func)
    set_logging_metadata(wrapper, func, _build_logging_payload(param))
    return wrapper  # type: ignore[return-value]


@overload
def with_context(func: _F) -> _F: ...


@overload
def with_context(*, param: str = ...) -> Callable[[_F], _F]: ...


def with_context(
    func: _F | None = None,
    *,
    param: str = _DEFAULT_PARAM,
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
    """

    def decorator(fn: _F) -> _F:
        if asyncio.iscoroutinefunction(fn):
            return _wrap_async(fn, param)
        return _wrap_sync(fn, param)

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
