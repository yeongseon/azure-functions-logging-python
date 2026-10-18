"""Handler-local ``LogRecord`` transformation isolation."""

from __future__ import annotations

from contextvars import ContextVar
import copy
from dataclasses import dataclass
import logging
from typing import Any

_COPY_MAX_DEPTH = 32
_COPY_MAX_NODES = 4096
_COPY_LIMIT_SENTINEL = "<copy-limit>"

#: Standard LogRecord fields the logging machinery and downstream
#: formatters/handlers need verbatim, regardless of how large a sibling
#: payload field is: level comparison (IsolatedHandler.emit), timestamp
#: formatting, caller identification, and exception handling all depend on
#: these keeping their original, uncorrupted types. Never passed through
#: the bounded copier -- a wide `args`/extra payload must not be able to
#: exhaust the shared budget and turn e.g. the numeric `levelno` into the
#: sentinel string (#580).
_CONTROL_FIELDS = frozenset(
    {
        "name",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",  # Python 3.12+; absent on 3.11, harmless to list here
        "exc_info",
        "exc_text",
        "stack_info",
    }
)


@dataclass(slots=True)
class _ForwardingState:
    handler_id: int
    active: bool = True


_forwarding_state: ContextVar[_ForwardingState | None] = ContextVar(
    "azure_functions_logging_isolated_forwarding_state", default=None
)


def _copy_mutable(
    value: Any,
    memo: dict[int, Any],
    budget: list[int],
    depth: int = 0,
) -> Any:
    if not isinstance(value, (dict, list, tuple)):
        # Scalars (int, str, float, bool, None, ...) need no copying at all
        # and must never consume -- or be rejected by -- the node budget;
        # only containers do.
        return value
    if depth > _COPY_MAX_DEPTH or budget[0] >= _COPY_MAX_NODES:
        return _COPY_LIMIT_SENTINEL
    budget[0] += 1
    value_id = id(value)
    if value_id in memo:
        return memo[value_id]
    if isinstance(value, dict):
        copied: dict[Any, Any] = {}
        memo[value_id] = copied
        for key, item in value.items():
            if budget[0] >= _COPY_MAX_NODES:
                # The budget bounds breadth (elements visited), not just
                # container nesting -- a wide, shallow payload (e.g. a
                # million scalar keys) must not bypass it just because
                # none of its leaves are themselves containers (#611).
                # Remaining entries are collapsed under one marker key
                # rather than copied one by one.
                copied[_COPY_LIMIT_SENTINEL] = _COPY_LIMIT_SENTINEL
                break
            budget[0] += 1
            copied[_copy_mutable(key, memo, budget, depth + 1)] = _copy_mutable(
                item, memo, budget, depth + 1
            )
        return copied
    if isinstance(value, list):
        copied_list: list[Any] = []
        memo[value_id] = copied_list
        for item in value:
            if budget[0] >= _COPY_MAX_NODES:
                copied_list.append(_COPY_LIMIT_SENTINEL)
                break
            budget[0] += 1
            copied_list.append(_copy_mutable(item, memo, budget, depth + 1))
        return copied_list
    if isinstance(value, tuple):  # pragma: no branch — the only remaining case after dict/list
        copied_items: list[Any] = []
        for item in value:
            if budget[0] >= _COPY_MAX_NODES:
                copied_items.append(_COPY_LIMIT_SENTINEL)
                break
            budget[0] += 1
            copied_items.append(_copy_mutable(item, memo, budget, depth + 1))
        if value_id in memo:
            return memo[value_id]
        copied_tuple = tuple(copied_items)
        memo[value_id] = copied_tuple
        return copied_tuple


def _copy_record(record: logging.LogRecord) -> logging.LogRecord:
    cloned = copy.copy(record)
    memo: dict[int, Any] = {}
    budget = [0]
    copied: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _CONTROL_FIELDS:
            # Preserved verbatim, never budget-bound: see _CONTROL_FIELDS.
            copied[key] = value
        elif key == "args":
            copied[key] = _copy_args(value, memo, budget)
        else:
            copied[key] = _copy_mutable(value, memo, budget)
    cloned.__dict__ = copied
    return cloned


def _copy_args(value: Any, memo: dict[int, Any], budget: list[int]) -> Any:
    """Copy ``LogRecord.args`` with a safe bound-reached fallback.

    If the budget is already exhausted when ``args`` itself is reached,
    ``_copy_mutable`` would return the bare sentinel *string* in its place.
    A format string with multiple ``%`` placeholders expects a tuple (or a
    single mapping) for ``args``, so replacing the whole value with a
    string risks an interpolation ``TypeError`` of its own. Falling back to
    an empty tuple instead keeps ``LogRecord.getMessage()`` safe: ``args``
    becomes falsy, so interpolation is skipped entirely and the raw
    ``msg`` template renders unchanged -- lossy, but never raises (#580).
    """
    copied = _copy_mutable(value, memo, budget)
    if copied is _COPY_LIMIT_SENTINEL:
        return ()
    return copied


class IsolatedHandler(logging.Handler):
    """Run handler-local filters on a cloned record before forwarding it.

    Register this wrapper instead of ``target`` and attach mutating filters to
    the wrapper. The target remains caller-owned: closing this wrapper does not
    close the target, while ``flush()`` is forwarded.
    """

    def __init__(self, target: logging.Handler) -> None:
        super().__init__(logging.NOTSET)
        self.target = target

    def handle(self, record: logging.LogRecord) -> bool:
        handler_id = id(self)
        inherited_state = _forwarding_state.get()
        if (
            inherited_state is not None
            and inherited_state.active
            and inherited_state.handler_id == handler_id
        ):
            return False

        state = _ForwardingState(handler_id)
        token = _forwarding_state.set(state)
        try:
            cloned = _copy_record(record)
            filtered = self.filter(cloned)
            if not filtered:
                return False
            if isinstance(filtered, logging.LogRecord):
                cloned = filtered
            self.acquire()
            try:
                self.emit(cloned)
            finally:
                self.release()
            return True
        finally:
            state.active = False
            _forwarding_state.reset(token)

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= self.target.level:
            self.target.handle(record)

    def flush(self) -> None:
        """Flush the wrapped target without transferring close ownership."""
        self.target.flush()
