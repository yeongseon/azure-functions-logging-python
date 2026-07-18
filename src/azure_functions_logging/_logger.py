"""FunctionLogger wrapper for azure-functions-logging."""

from __future__ import annotations

import logging
from typing import Any

from ._constants import _FORWARD_COMPAT_RECORD_KEYS as _FORWARD_COMPAT_RECORD_KEYS
from ._constants import _LIBRARY_RESERVED_KEYS as _LIBRARY_RESERVED_KEYS
from ._constants import _RESERVED_LOG_RECORD_KEYS as _RESERVED_LOG_RECORD_KEYS
from ._constants import _STDLIB_RECORD_KEYS as _STDLIB_RECORD_KEYS


def _sanitize_extra(extra: dict[str, Any]) -> dict[str, Any]:
    """Rename keys that collide with reserved ``LogRecord`` attributes.

    ``logging.Logger._log`` raises ``KeyError`` if ``extra`` contains a key that
    shadows a built-in record attribute. Rather than crash the user's code, we
    prefix the offending keys with ``extra_`` so the value still reaches the
    formatter under a deterministic name.
    """
    if not extra:
        return extra
    if not any(key in _RESERVED_LOG_RECORD_KEYS for key in extra):
        return extra
    sanitized: dict[str, Any] = {}
    for key, value in extra.items():
        if key in _RESERVED_LOG_RECORD_KEYS:
            target = f"extra_{key}"
            if target in sanitized:
                suffix = 2
                while f"{target}_{suffix}" in sanitized:
                    suffix += 1
                target = f"{target}_{suffix}"
            sanitized[target] = value
        else:
            if key in sanitized:
                suffix = 2
                while f"{key}_{suffix}" in sanitized:
                    suffix += 1
                key = f"{key}_{suffix}"
            sanitized[key] = value
    return sanitized


class FunctionLogger:
    """Wrapper around a standard ``logging.Logger`` with context binding.

    ``FunctionLogger`` delegates all standard logging methods to the underlying
    logger. The ``bind()`` method returns a new wrapper with additional context
    fields that are merged into ``extra`` on each log call.

    Context from ``bind()`` is supplementary to the ``ContextFilter``-based
    context (invocation_id, function_name, etc.) which is set globally via
    ``inject_context()``.
    """

    __slots__ = ("_logger", "_context")

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._context: dict[str, Any] = {}

    @property
    def name(self) -> str:
        """Return the name of the underlying logger."""
        return self._logger.name

    def bind(self, **kwargs: Any) -> FunctionLogger:
        """Return a new ``FunctionLogger`` with additional bound context.

        The returned logger shares the same underlying ``logging.Logger``
        but carries merged context fields. This is an immutable operation.

        Args:
            **kwargs: Context key-value pairs to bind.

        Returns:
            A new ``FunctionLogger`` with merged context.
        """
        new = FunctionLogger(self._logger)
        new._context = {**self._context, **kwargs}
        return new

    def clear_context(self) -> None:
        """Clear all bound context fields."""
        self._context = {}

    def _log(
        self,
        level: int,
        msg: object,
        args: tuple[Any, ...],
        exc_info: Any = None,
        stack_info: bool = False,
        stacklevel: int = 2,
        **kwargs: Any,
    ) -> None:
        """Internal log dispatch with context injection."""
        if not self._logger.isEnabledFor(level):
            return
        explicit_extra = kwargs.pop("extra", None) or {}
        extra = {**self._context, **explicit_extra, **kwargs}
        extra = _sanitize_extra(extra)
        self._logger.log(
            level,
            msg,
            *args,
            exc_info=exc_info,
            stack_info=stack_info,
            stacklevel=stacklevel,
            extra=extra,
        )

    def debug(self, msg: object, *args: Any, **kwargs: Any) -> None:
        """Log a DEBUG message."""
        self._log(logging.DEBUG, msg, args, **kwargs)

    def info(self, msg: object, *args: Any, **kwargs: Any) -> None:
        """Log an INFO message."""
        self._log(logging.INFO, msg, args, **kwargs)

    def warning(self, msg: object, *args: Any, **kwargs: Any) -> None:
        """Log a WARNING message."""
        self._log(logging.WARNING, msg, args, **kwargs)

    def error(self, msg: object, *args: Any, **kwargs: Any) -> None:
        """Log an ERROR message."""
        self._log(logging.ERROR, msg, args, **kwargs)

    def critical(self, msg: object, *args: Any, **kwargs: Any) -> None:
        """Log a CRITICAL message."""
        self._log(logging.CRITICAL, msg, args, **kwargs)

    def exception(self, msg: object, *args: Any, **kwargs: Any) -> None:
        """Log an ERROR message with exception info."""
        kwargs["exc_info"] = kwargs.get("exc_info", True)
        self._log(logging.ERROR, msg, args, **kwargs)

    def setLevel(self, level: int | str) -> None:
        """Set the logging level of the underlying logger."""
        self._logger.setLevel(level)

    def isEnabledFor(self, level: int) -> bool:
        """Check if the underlying logger is enabled for the given level."""
        return self._logger.isEnabledFor(level)

    def getEffectiveLevel(self) -> int:
        """Return the effective level of the underlying logger."""
        return self._logger.getEffectiveLevel()

    def log(self, level: int, msg: object, *args: Any, **kwargs: Any) -> None:
        """Log ``msg`` at the given ``level``, mirroring ``logging.Logger.log``.

        Honors the same ``bind`` < ``extra`` < ``kwargs`` merge precedence
        as :meth:`info` / :meth:`warning` / etc. and applies the same
        reserved-key sanitization.
        """
        self._log(level, msg, args, **kwargs)

    def hasHandlers(self) -> bool:
        """Return whether the underlying logger has any handlers configured."""
        return self._logger.hasHandlers()
