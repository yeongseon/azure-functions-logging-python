"""Record sanitization for every redaction profile, on top of the shared value engine."""

from collections.abc import Mapping
import json
import logging
import re
import traceback

from . import _secure_values
from ._constants import _RESERVED_LOG_RECORD_KEYS, _STDLIB_RECORD_KEYS
from ._redaction import DEFAULT_PATTERNS, MASK, is_sensitive
from ._redaction import mask_patterns as _mask_patterns
from ._secure_values import RedactionProfile, ValueMasker


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


def _sanitize_closed(record: logging.LogRecord, profile: RedactionProfile) -> bool:
    keys, patterns = profile.keys, profile.patterns
    masker = ValueMasker(profile)
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


def _legacy_message(record: logging.LogRecord, profile: RedactionProfile) -> None:
    """Mask secrets embedded in the rendered message; preserve the record on any error."""
    try:
        rendered = record.getMessage()
        masked = rendered
        try:
            parsed = json.loads(rendered)
            if isinstance(parsed, (dict, list)):
                # Key-based only: patterns are applied to the whole rendered text below.
                keys_only = ValueMasker(RedactionProfile(profile.keys))
                masked = json.dumps(keys_only.mask(parsed), separators=(",", ":"))
        except (json.JSONDecodeError, TypeError):
            pass
        if profile.patterns:
            masked = _mask_patterns(masked, profile.patterns)
        if masked != rendered:
            record.msg = masked
            record.args = ()
    except Exception:  # nosec B110 -- message masking must never raise
        pass


def _legacy_exception(record: logging.LogRecord, profile: RedactionProfile) -> None:
    """Render and mask exception text before a formatter can expose it."""
    if record.exc_info is None and record.exc_text is None:
        return
    try:
        patterns = (*DEFAULT_PATTERNS, *profile.patterns)
        if record.exc_info is not None:
            exc_type, exc_value, _ = record.exc_info
            if exc_type is None:
                return
            rendered = "".join(traceback.format_exception(*record.exc_info))
            message = "".join(traceback.format_exception_only(exc_type, exc_value)).strip()
            record.exc_text = _mask_patterns(rendered, patterns)
            setattr(record, "exception.type", exc_type.__name__)
            setattr(record, "exception.message", _mask_patterns(message, patterns))
            setattr(record, "exception.stacktrace", record.exc_text)
        elif record.exc_text is not None:
            record.exc_text = _mask_patterns(record.exc_text, patterns)
        record.exc_info = None
    except Exception:  # nosec B110 -- exception masking must never raise
        pass


def _sanitize_legacy(record: logging.LogRecord, profile: RedactionProfile) -> bool:
    masker = ValueMasker(profile)
    try:
        for key in list(record.__dict__.keys()):
            try:
                if key in _RESERVED_LOG_RECORD_KEYS:
                    continue
                if is_sensitive(key, profile.keys):
                    setattr(record, key, MASK)
                    continue
                value = record.__dict__[key]
                if isinstance(value, (dict, list, tuple)):
                    setattr(record, key, masker.mask(value))
                elif profile.patterns and isinstance(value, str):
                    setattr(record, key, _mask_patterns(value, profile.patterns))
            except Exception:  # nosec B110 -- one broken field must not stop others
                pass
        _legacy_message(record, profile)
        _legacy_exception(record, profile)
    except Exception:  # nosec B110 -- filter must never raise
        pass
    return True


def sanitize_record(record: logging.LogRecord, profile: RedactionProfile) -> bool:
    """Sanitize *record* in place under *profile*; always returns True (never drops)."""
    return (
        _sanitize_closed(record, profile)
        if profile.fail_closed
        else _sanitize_legacy(record, profile)
    )
