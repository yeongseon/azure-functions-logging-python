"""Log formatters for azure-functions-logging."""

from __future__ import annotations

import logging
import sys
from typing import Iterable

from ._constants import _LIBRARY_RESERVED_KEYS, _STDLIB_RECORD_KEYS
from ._redaction import mask_value

# ANSI color codes
_COLORS: dict[int, str] = {
    logging.DEBUG: "\033[90m",  # Gray
    logging.INFO: "\033[34m",  # Blue
    logging.WARNING: "\033[33m",  # Yellow
    logging.ERROR: "\033[31m",  # Red
    logging.CRITICAL: "\033[1;31m",  # Bold Red
}
_RESET = "\033[0m"


_STANDARD_RECORD_FIELDS: frozenset[str] = _STDLIB_RECORD_KEYS
_CONTEXT_FIELDS: frozenset[str] = _LIBRARY_RESERVED_KEYS


class ColorFormatter(logging.Formatter):
    """Colorized log formatter for local development.

    Format: ``HH:MM:SS LEVEL  logger_name  message [context_fields]``

    Context fields (invocation_id, function_name, etc.) are appended
    when present on the LogRecord (set by ContextFilter).

    Args:
        include_extra: When True, appends ``bind()`` context fields (extra
            attributes on the LogRecord) to the formatted output. Sensitive
            values are masked with ``"***"`` using the shared redaction rules
            (see ``mask_value``), which cover the full default sensitive-key
            set (e.g. ``password``, ``token``, ``access_token``,
            ``refresh_token``, ``authorization``, ``secret``, ``api_key``,
            ``connection_string``, ``x_functions_key``, ...) and normalize
            hyphenated header forms, so keys like ``X-Functions-Key`` also
            match. Default: False.
        extra_allowlist: Optional set of extra field names to include. When
            provided, only keys in this set are shown (sensitive keys are
            still masked). When None (default), all non-standard fields are
            included if ``include_extra=True``.
    """

    def __init__(
        self,
        *,
        include_extra: bool = False,
        extra_allowlist: Iterable[str] | None = None,
    ) -> None:
        super().__init__()
        self._include_extra = include_extra
        self._extra_allowlist: frozenset[str] | None = (
            frozenset(extra_allowlist) if extra_allowlist is not None else None
        )

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with colors and context fields."""
        # Time
        time_str = self.formatTime(record, "%H:%M:%S")

        # Level with color
        color = _COLORS.get(record.levelno, "")
        level_str = f"{color}{record.levelname:<8}{_RESET}"

        # Logger name
        name_str = record.name

        # Message
        msg = record.getMessage()

        # Context fields
        context_parts: list[str] = []
        for field in ("invocation_id", "function_name", "trace_id"):
            value = getattr(record, field, None)
            if value is not None:
                context_parts.append(f"{field}={value}")

        cold_start = getattr(record, "cold_start", None)
        if cold_start is True:
            context_parts.append("cold_start=true")

        # Extra bind() fields
        if self._include_extra:
            excluded = _STANDARD_RECORD_FIELDS | _CONTEXT_FIELDS
            for key, value in record.__dict__.items():
                if key in excluded:
                    continue
                if self._extra_allowlist is not None and key not in self._extra_allowlist:
                    continue
                masked_value = mask_value(key, value)
                context_parts.append(f"{key}={masked_value}")

        # Build output
        base = f"{time_str} {level_str} {name_str}  {msg}"
        if context_parts:
            base += f"  [{', '.join(context_parts)}]"

        # Exception info
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            base += f"\n{record.exc_text}"
        if record.stack_info:
            base += f"\n{record.stack_info}"

        return base

    @staticmethod
    def is_tty() -> bool:
        """Check if stderr supports color output."""
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
