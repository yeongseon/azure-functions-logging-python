"""Handler-local ``LogRecord`` transformation isolation."""

from __future__ import annotations

from contextvars import ContextVar
import copy
import logging
from typing import Any

_active_handlers: ContextVar[frozenset[int]] = ContextVar(
    "azure_functions_logging_active_isolated_handlers", default=frozenset()
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
        copied_tuple = tuple(_copy_mutable(item, memo) for item in value)
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
        super().__init__(target.level)
        self.target = target

    def handle(self, record: logging.LogRecord) -> bool:
        handler_id = id(self)
        active = _active_handlers.get()
        if handler_id in active:
            return False

        token = _active_handlers.set(active | {handler_id})
        try:
            cloned = _copy_record(record)
            if not self.filter(cloned):
                return False
            self.acquire()
            try:
                self.emit(cloned)
            finally:
                self.release()
            return True
        finally:
            _active_handlers.reset(token)

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= self.target.level:
            self.target.handle(record)

    def flush(self) -> None:
        """Flush the wrapped target without transferring close ownership."""
        self.target.flush()
