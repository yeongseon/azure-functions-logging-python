"""Opt-in fail-closed record sanitization before downstream formatting/export."""

from collections.abc import Mapping
import json
import logging
import re
import traceback

from . import _secure_values
from ._constants import _STDLIB_RECORD_KEYS
from ._redaction import DEFAULT_PATTERNS, MASK, is_sensitive
from ._secure_values import ValueMasker


def _failed_message(record: logging.LogRecord) -> None:
    record.__dict__.update(
        msg="[REDACTION FAILED]", args=(), exc_info=None, exc_text=None, stack_info=None
    )
    if "message" in record.__dict__:
        record.__dict__["message"] = "[REDACTION FAILED]"
    for key in ("exception.message", "exception.stacktrace"):
        if key in record.__dict__:
            record.__dict__[key] = MASK


def _message(record: logging.LogRecord, masker: ValueMasker) -> None:
    try:
        if not isinstance(record.msg, str):
            record.__dict__["msg"] = masker.mask(record.msg)
        if isinstance(record.args, Mapping):
            record.__dict__["args"] = masker.mask(record.args)
        elif isinstance(record.args, tuple):
            record.__dict__["args"] = tuple(
                masker.mask(arg) if isinstance(arg, (Mapping, list, tuple)) else arg
                for arg in record.args
            )
        rendered = record.getMessage()
        try:
            parsed = json.loads(rendered)
        except (ValueError, TypeError, RecursionError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            sanitized = masker.mask(parsed)
            if sanitized != parsed:
                rendered = json.dumps(sanitized, separators=(",", ":"))
        record.__dict__.update(msg=_secure_values.mask_text(rendered, masker.patterns), args=())
        if "message" in record.__dict__:
            record.__dict__["message"] = record.msg
    except Exception:
        # Rendering and regex callbacks may execute arbitrary user code.
        _failed_message(record)


def _exception(record: logging.LogRecord, patterns: tuple[re.Pattern[str], ...]) -> None:
    try:
        if record.exc_info is not None:
            kind, value, _ = record.exc_info
            rendered = "".join(traceback.format_exception(*record.exc_info))
            message = "".join(traceback.format_exception_only(kind, value)).strip()
            record.__dict__.update(
                {
                    "exc_text": _secure_values.mask_text(rendered, patterns),
                    "exception.type": kind.__name__ if kind is not None else MASK,
                    "exception.message": _secure_values.mask_text(message, patterns),
                    "exception.stacktrace": _secure_values.mask_text(rendered, patterns),
                }
            )
        elif record.exc_text is not None:
            record.__dict__["exc_text"] = _secure_values.mask_text(record.exc_text, patterns)
        if record.stack_info is not None:
            record.__dict__["stack_info"] = _secure_values.mask_text(record.stack_info, patterns)
    except Exception:
        # Never forward raw exception objects after a diagnostic conversion failure.
        record.__dict__.update(
            {
                "exc_text": MASK,
                "stack_info": None,
                "exception.message": MASK,
                "exception.stacktrace": MASK,
            }
        )
    finally:
        record.__dict__["exc_info"] = None


def sanitize_record(
    record: logging.LogRecord, keys: frozenset[str], patterns: tuple[re.Pattern[str], ...]
) -> bool:
    masker = ValueMasker(keys, patterns)
    try:
        for key in tuple(record.__dict__):
            if key in _STDLIB_RECORD_KEYS and key not in {
                "name",
                "threadName",
                "processName",
                "pathname",
                "filename",
                "module",
                "funcName",
                "levelname",
                "taskName",
            }:
                continue
            value = record.__dict__[key]
            record.__dict__[key] = MASK if is_sensitive(key, keys) else masker.mask(value)
        _message(record, masker)
        _exception(record, (*patterns, *DEFAULT_PATTERNS))
    except Exception:
        # Malformed custom LogRecords cannot force the original payload to a sink.
        record.__dict__ = {k: v for k, v in record.__dict__.items() if k in _STDLIB_RECORD_KEYS}
        _failed_message(record)
    return True
