"""Handler-local ``LogRecord`` transformation isolation."""

from __future__ import annotations

from contextvars import ContextVar
import copy
from dataclasses import dataclass
import logging
from typing import Any


@dataclass(slots=True)
class _ForwardingState:
    handler_id: int
    active: bool = True


_forwarding_state: ContextVar[_ForwardingState | None] = ContextVar(
    "azure_functions_logging_isolated_forwarding_state", default=None
)


def _copy_mutable(value: Any, memo: dict[int, Any]) -> Any:
    value_id = id(value)
    if value_id in memo:
        return memo[value_id]
    if isinstance(value, dict):
        copied: dict[Any, Any] = {}
        memo[value_id] = copied
        copied.update(
            (_copy_mutable(key, memo), _copy_mutable(item, memo)) for key, item in value.items()
        )
        return copied
    if isinstance(value, list):
        copied_list: list[Any] = []
        memo[value_id] = copied_list
        copied_list.extend(_copy_mutable(item, memo) for item in value)
        return copied_list
    if isinstance(value, tuple):
        copied_items = [_copy_mutable(item, memo) for item in value]
        if value_id in memo:
            return memo[value_id]
        copied_tuple = tuple(copied_items)
        memo[value_id] = copied_tuple
        return copied_tuple
    return value


def _copy_record(record: logging.LogRecord) -> logging.LogRecord:
    cloned = copy.copy(record)
    memo: dict[int, Any] = {}
    cloned.__dict__ = {key: _copy_mutable(value, memo) for key, value in record.__dict__.items()}
    return cloned


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
