"""Characterization (golden) tests pinning observable redaction behavior.

The corpus runs every case through the legacy best-effort profile (with and
without patterns) and the fail-closed secure profile. ``tests/data/
redaction_characterization.json`` was recorded from the implementation *before*
the single-engine refactor, so any behavior drift fails here.
"""

from collections import UserDict
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any

import pytest

from azure_functions_logging import DEFAULT_REDACTION_PATTERNS, RedactionFilter
from azure_functions_logging._secure import _SecureRedactionFilter

GOLDEN = Path(__file__).parent / "data" / "redaction_characterization.json"
CANARY = "CANARY_CHAR"
_VOLATILE = {
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "process",
    "processName",
    "lineno",
    "pathname",
    "filename",
    "module",
    "funcName",
    "taskName",
    "levelno",
    "levelname",
    "name",
}


class Opaque:
    def __repr__(self) -> str:
        return f"Opaque(password={CANARY})"


class BadRepr:
    def __repr__(self) -> str:
        raise RuntimeError(CANARY)


class BadItems(dict):  # type: ignore[type-arg]
    def items(self) -> Any:
        raise RuntimeError(CANARY)


class BadMapping(UserDict):  # type: ignore[type-arg]
    def items(self) -> Any:
        raise RuntimeError(CANARY)


class BadStr:
    def __repr__(self) -> str:
        return "BadStr()"

    def __str__(self) -> str:
        raise RuntimeError(CANARY)


def _deep(n: int) -> dict[str, Any]:
    out: dict[str, Any] = {"leaf": f"token={CANARY}"}
    for _ in range(n):
        out = {"n": out}
    return out


def _cyclic() -> dict[str, Any]:
    d: dict[str, Any] = {"a": 1}
    d["self"] = d
    return d


def _cyclic_list() -> list[Any]:
    x: list[Any] = [1]
    x.append(x)
    return x


def _exc_record(secret: str) -> logging.LogRecord:
    # No traceback object: keeps rendered text independent of paths and line numbers.
    error = ValueError(f"password={secret}")
    return logging.makeLogRecord({"msg": "failed", "exc_info": (ValueError, error, None)})


_JSON_MSG = json.dumps({"password": CANARY, "ok": 1, "nested": {"token": CANARY}})

CASES: dict[str, Any] = {
    "plain": lambda: logging.makeLogRecord({"msg": "hello"}),
    "sensitive_extra": lambda: logging.makeLogRecord({"msg": "m", "password": CANARY, "ok": "v"}),
    "dotted_sensitive": lambda: logging.makeLogRecord({"msg": "m", "order.password": CANARY}),
    "nested_dict": lambda: logging.makeLogRecord(
        {"msg": "m", "payload": {"user": "u", "password": CANARY, "inner": {"Api-Key": CANARY}}}
    ),
    "headers": lambda: logging.makeLogRecord(
        {"msg": "m", "headers": {"Authorization": f"Bearer {CANARY}", "X-Functions-Key": CANARY}}
    ),
    "list_of_dicts": lambda: logging.makeLogRecord(
        {"msg": "m", "items": [{"token": CANARY}, {"k": f"secret={CANARY}"}]}
    ),
    "tuple_value": lambda: logging.makeLogRecord(
        {"msg": "m", "t": ({"secret": CANARY}, f"token={CANARY}")}
    ),
    "set_value": lambda: logging.makeLogRecord({"msg": "m", "s": {f"token={CANARY}"}}),
    "frozenset_value": lambda: logging.makeLogRecord(
        {"msg": "m", "s": frozenset({f"token={CANARY}"})}
    ),
    "string_extra": lambda: logging.makeLogRecord({"msg": "m", "note": f"password={CANARY}"}),
    "str_subclass": lambda: logging.makeLogRecord(
        {"msg": "m", "note": type("S", (str,), {})(f"password={CANARY}")}
    ),
    "numbers_bool_none": lambda: logging.makeLogRecord(
        {"msg": "m", "a": 1, "b": 1.5, "c": True, "d": None}
    ),
    "bytes_value": lambda: logging.makeLogRecord({"msg": "m", "b": f"token={CANARY}".encode()}),
    "opaque": lambda: logging.makeLogRecord({"msg": "m", "o": Opaque()}),
    "opaque_in_list": lambda: logging.makeLogRecord({"msg": "m", "o": [Opaque(), 1]}),
    "bad_repr": lambda: logging.makeLogRecord({"msg": "m", "o": BadRepr()}),
    "bad_repr_in_dict": lambda: logging.makeLogRecord({"msg": "m", "o": {"x": BadRepr()}}),
    "bad_items_dict": lambda: logging.makeLogRecord({"msg": "m", "o": BadItems(a=1)}),
    "bad_mapping": lambda: logging.makeLogRecord({"msg": "m", "o": BadMapping(a=1)}),
    "userdict": lambda: logging.makeLogRecord({"msg": "m", "o": UserDict({"password": CANARY})}),
    "non_str_keys": lambda: logging.makeLogRecord(
        {"msg": "m", "o": {1: "a", ("t",): f"token={CANARY}", "password": CANARY}}
    ),
    "sensitive_key_variants": lambda: logging.makeLogRecord(
        {"msg": "m", "o": {"clientSecret": CANARY, "X-Api-Key": CANARY, "PASSWORD": CANARY}}
    ),
    "deep_9": lambda: logging.makeLogRecord({"msg": "m", "d": _deep(9)}),
    "deep_10": lambda: logging.makeLogRecord({"msg": "m", "d": _deep(10)}),
    "deep_30": lambda: logging.makeLogRecord({"msg": "m", "d": _deep(30)}),
    "cyclic_dict": lambda: logging.makeLogRecord({"msg": "m", "c": _cyclic()}),
    "cyclic_list": lambda: logging.makeLogRecord({"msg": "m", "c": _cyclic_list()}),
    "shared_not_cyclic": lambda: logging.makeLogRecord(
        {"msg": "m", "c": [(s := {"a": 1}), s, [s]]}
    ),
    "wide_list": lambda: logging.makeLogRecord({"msg": "m", "w": list(range(5000))}),
    "wide_dict": lambda: logging.makeLogRecord({"msg": "m", "w": {str(i): i for i in range(5000)}}),
    "huge_string": lambda: logging.makeLogRecord({"msg": "m", "h": "x" * 70000}),
    "huge_message": lambda: logging.makeLogRecord({"msg": "y" * 70000 + f" token={CANARY}"}),
    "msg_secret": lambda: logging.makeLogRecord({"msg": f"connect password={CANARY} done"}),
    "msg_percent_args": lambda: logging.makeLogRecord(
        {"msg": "login %s ok", "args": (f"token={CANARY}",)}
    ),
    "msg_mapping_args": lambda: logging.makeLogRecord(
        {"msg": "u=%(user)s p=%(password)s", "args": {"user": "a", "password": CANARY}}
    ),
    "msg_args_dict_in_tuple": lambda: logging.makeLogRecord(
        {"msg": "x %s", "args": ({"password": CANARY},)}
    ),
    "msg_args_list_in_tuple": lambda: logging.makeLogRecord(
        {"msg": "x %s", "args": ([f"token={CANARY}"],)}
    ),
    "msg_args_mismatch": lambda: logging.makeLogRecord(
        {"msg": "x %s %s", "args": (f"token={CANARY}",)}
    ),
    "msg_object": lambda: logging.makeLogRecord({"msg": {"password": CANARY}}),
    "msg_object_str": lambda: logging.makeLogRecord({"msg": Opaque()}),
    "msg_bad_str": lambda: logging.makeLogRecord({"msg": BadStr()}),
    "msg_json": lambda: logging.makeLogRecord({"msg": _JSON_MSG}),
    "msg_json_list": lambda: logging.makeLogRecord({"msg": json.dumps([{"password": CANARY}])}),
    "msg_json_scalar": lambda: logging.makeLogRecord({"msg": "123"}),
    "msg_json_deep": lambda: logging.makeLogRecord(
        {"msg": json.dumps(_deep(14), separators=(",", ":"))}
    ),
    "exception": lambda: _exc_record(CANARY),
    "exception_prerendered": lambda: logging.makeLogRecord(
        {"msg": "e", "exc_text": f"Traceback password={CANARY}"}
    ),
    "stack_info": lambda: logging.makeLogRecord(
        {"msg": "e", "stack_info": f"Stack token={CANARY}"}
    ),
    "exc_info_none_tuple": lambda: logging.makeLogRecord(
        {"msg": "e", "exc_info": (None, None, None)}
    ),
    "message_attr_set": lambda: logging.makeLogRecord(
        {"msg": f"password={CANARY}", "message": f"password={CANARY}"}
    ),
    "reserved_context_extra": lambda: logging.makeLogRecord(
        {"msg": "m", "invocation_id": "id-1", "function_name": "f", "trace_id": "t"}
    ),
    "flattened_dotted_nested_key": lambda: logging.makeLogRecord(
        {"msg": "m", "token.raw": CANARY, "order.id": 3, "metrics.token_count": 7}
    ),
    "custom_pattern_text": lambda: logging.makeLogRecord({"msg": "m", "n": "ssn 123-45-6789"}),
    "azure_secrets": lambda: logging.makeLogRecord(
        {
            "msg": "m",
            "conn": f"AccountKey={CANARY};Endpoint=x",
            "jwt": "eyJabc.def.ghi",
            "gh": "ghp_" + "a" * 24,
        }
    ),
    "quoted_secret": lambda: logging.makeLogRecord({"msg": f"password='{CANARY}'"}),
    "basic_auth": lambda: logging.makeLogRecord({"msg": f"authorization: Basic {CANARY}"}),
}


def _filters() -> dict[str, Any]:
    return {
        "legacy_nopat": RedactionFilter(),
        "legacy_default_patterns": RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS),
        "legacy_custom": RedactionFilter(
            sensitive_keys=["note", "ssn_key"], patterns=[re.compile(r"\d{3}-\d{2}-\d{4}")]
        ),
        "closed_default": RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS, fail_closed=True),
        "closed_no_patterns": RedactionFilter(fail_closed=True),
        "secure": _SecureRedactionFilter(),
    }


def _snapshot(record: logging.LogRecord) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in sorted(record.__dict__.items()):
        if key in _VOLATILE:
            continue
        try:
            text = repr(value)
        except Exception:  # pragma: no cover - snapshot helper only
            text = "<unrepresentable>"
        if len(text) > 300:  # keep the golden file small: pin length and content digest
            text = f"<len={len(text)} sha256={hashlib.sha256(text.encode()).hexdigest()[:20]}>"
        out[key] = text
    try:
        out["<getMessage>"] = record.getMessage()
    except Exception as exc:
        out["<getMessage>"] = f"<raises {type(exc).__name__}>"
    return out


def compute() -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    for fname in _filters():
        result[fname] = {}
        for cname, make in CASES.items():
            record = make()
            flt = _filters()[fname]
            returned = flt.filter(record)
            snap = _snapshot(record)
            snap["<returned>"] = repr(returned)
            result[fname][cname] = snap
    return result


def _golden() -> dict[str, dict[str, dict[str, str]]]:
    return json.loads(GOLDEN.read_text())  # type: ignore[no-any-return]


_COMPUTED = compute() if GOLDEN.exists() else {}


@pytest.mark.parametrize("fname", list(_filters()))
@pytest.mark.parametrize("cname", list(CASES))
def test_redaction_output_matches_recorded_baseline(fname: str, cname: str) -> None:
    assert _COMPUTED[fname][cname] == _golden()[fname][cname]


@pytest.mark.parametrize("fail_closed", [False, True])
def test_every_profile_traverses_through_the_single_shared_engine(
    monkeypatch: pytest.MonkeyPatch, fail_closed: bool
) -> None:
    from azure_functions_logging import _secure_values

    calls: list[bool] = []
    original = _secure_values.ValueMasker.mask

    def spy(self: Any, *args: Any, **kwargs: Any) -> object:
        calls.append(self.profile.fail_closed)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(_secure_values.ValueMasker, "mask", spy)
    record = logging.makeLogRecord({"msg": "m", "payload": {"password": CANARY}})
    RedactionFilter(fail_closed=fail_closed).filter(record)
    assert calls
    assert set(calls) == {fail_closed}
    assert record.__dict__["payload"]["password"] == "***"


def test_no_second_recursive_converter_remains_in_filters() -> None:
    from azure_functions_logging import _filters

    assert not hasattr(_filters, "_redact_value")
