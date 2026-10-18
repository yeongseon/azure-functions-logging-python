from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context, copy_context
import copy
import io
import json
import logging
import sys
from typing import TypedDict

import anyio
import pytest

from azure_functions_logging import (
    AttributeFlattenFilter,
    IsolatedHandler,
    JsonFormatter,
    RedactionFilter,
)


class _CollectingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.flush_count = 0
        self.close_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.close_count += 1
        super().close()


class _Cycle(TypedDict):
    shared: dict[str, int]
    self: _Cycle | None


class _PipelineFailure(RuntimeError):
    pass


def _replace_message(message: str) -> Callable[[logging.LogRecord], logging.LogRecord]:
    def replace(record: logging.LogRecord) -> logging.LogRecord:
        replacement = copy.copy(record)
        replacement.msg = message
        replacement.args = ()
        return replacement

    return replace


def _pipeline(
    name: str, isolated_first: bool
) -> tuple[logging.Logger, _CollectingHandler, io.StringIO]:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    target = _CollectingHandler()
    isolated = IsolatedHandler(target)
    isolated.addFilter(RedactionFilter())
    isolated.addFilter(AttributeFlattenFilter())

    stream = io.StringIO()
    plain = logging.StreamHandler(stream)
    plain.setFormatter(JsonFormatter())
    plain.addFilter(RedactionFilter())
    logger.handlers.extend([isolated, plain] if isolated_first else [plain, isolated])
    return logger, target, stream


@pytest.mark.parametrize("isolated_first", [True, False])
def test_isolated_handler_preserves_nested_json_in_both_orders(isolated_first: bool) -> None:
    # Given
    logger, target, stream = _pipeline(f"isolated.order.{isolated_first}", isolated_first)
    payload = {"id": 7, "password": "secret"}

    # When
    logger.info("order %s", "created", extra={"order": payload})

    # Then
    assert len(target.records) == 1
    assert target.records[0].getMessage() == "order created"
    assert target.records[0].__dict__["order.id"] == 7
    assert target.records[0].__dict__["order.password"] == "***"
    assert json.loads(stream.getvalue())["extra"]["order"] == {"id": 7, "password": "***"}
    assert payload == {"id": 7, "password": "secret"}


def test_isolated_handler_preserves_shared_references_and_cycles() -> None:
    # Given
    logger, target, _ = _pipeline("isolated.references", True)
    shared = {"value": 3}
    cycle = _Cycle(shared=shared, self=None)
    cycle["self"] = cycle

    # When
    logger.info("references", extra={"left": shared, "right": shared, "cycle": cycle})

    # Then
    record = target.records[0]
    assert record.__dict__["left.value"] == 3
    assert record.__dict__["right.value"] == 3
    assert record.__dict__["left.value"] == record.__dict__["right.value"]
    assert cycle["self"] is cycle


def test_isolated_handler_preserves_correlation_fields() -> None:
    # Given
    logger, target, _ = _pipeline("isolated.correlation", True)

    # When
    logger.info(
        "correlated",
        extra={"invocation_id": "inv-1", "function_name": "orders", "trace_id": "trace-1"},
    )

    # Then
    record = target.records[0]
    assert record.__dict__["invocation_id"] == "inv-1"
    assert record.__dict__["function_name"] == "orders"
    assert record.__dict__["trace_id"] == "trace-1"


def test_isolated_handler_prevents_recursive_forwarding() -> None:
    # Given
    logger = logging.getLogger("isolated.recursion")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    target = _CollectingHandler()
    handler = IsolatedHandler(target)
    target.addFilter(lambda _record: not handler.handle(logging.makeLogRecord({"msg": "nested"})))
    logger.addHandler(handler)

    # When
    logger.info("outer")

    # Then
    assert [record.getMessage() for record in target.records] == ["outer"]


def test_isolated_handler_uses_live_target_level() -> None:
    # Given
    target = _CollectingHandler()
    target.setLevel(logging.WARNING)
    handler = IsolatedHandler(target)
    logger = logging.getLogger("isolated.live-level")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    target.setLevel(logging.INFO)

    # When
    logger.info("accepted")

    # Then
    assert [record.getMessage() for record in target.records] == ["accepted"]


def test_isolated_handler_does_not_leak_guard_into_copied_context() -> None:
    # Given
    target = _CollectingHandler()
    copied_contexts: list[Context] = []

    def capture_context(_record: logging.LogRecord) -> bool:
        copied_contexts.append(copy_context())
        return True

    target.addFilter(capture_context)
    handler = IsolatedHandler(target)
    first = logging.makeLogRecord({"msg": "first", "levelno": logging.INFO})
    second = logging.makeLogRecord({"msg": "second", "levelno": logging.INFO})

    # When
    handler.handle(first)
    copied_contexts[0].run(handler.handle, second)

    # Then
    assert len(copied_contexts) == 2


def test_isolated_handler_masks_tuple_list_cycle_fail_closed() -> None:
    # Regression (#579): RedactionFilter now recurses into a top-level tuple
    # extra unconditionally (previously gated behind `patterns=`), so a
    # cyclic tuple/list now hits the same cycle-detection fail-closed mask
    # that dict cycles have always received -- it no longer passes through
    # untouched. This replaces the old identity-preservation assertion,
    # which only held because the pre-#579 bug skipped tuples entirely.
    # Given
    logger, target, _ = _pipeline("isolated.tuple-cycle", True)
    child: list[tuple[object, ...]] = []
    cycle: tuple[object, ...] = (child,)
    child.append(cycle)

    # When
    logger.info("cycle", extra={"cycle": cycle})

    # Then
    assert target.records[0].__dict__["cycle"] == (["***"],)
    # And the caller's own object is never mutated
    assert cycle[0] is child
    assert child[0] is cycle


def test_isolated_handler_applies_dotted_redaction_without_sibling_side_effects() -> None:
    # Given
    logger, target, stream = _pipeline("isolated.redaction", True)

    # When
    logger.info("secret", extra={"account.password": "secret"})

    # Then
    assert target.records[0].__dict__["account.password"] == "***"
    assert json.loads(stream.getvalue())["extra"]["account.password"] == "***"


def test_isolated_handler_preserves_record_metadata_and_target_filters() -> None:
    # Given
    target = _CollectingHandler()
    target.setLevel(logging.WARNING)
    target.addFilter(lambda record: record.__dict__.get("allowed") is True)
    handler = IsolatedHandler(target)
    logger = logging.getLogger("isolated.metadata")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # When
    logger.info("ignored", extra={"allowed": True})
    try:
        raise _PipelineFailure("boom")
    except _PipelineFailure:
        logger.exception("failure %s", "detail", extra={"allowed": True}, stack_info=True)
    logger.error("filtered", extra={"allowed": False})

    # Then
    assert len(target.records) == 1
    record = target.records[0]
    assert record.getMessage() == "failure detail"
    assert record.exc_info is not None
    assert record.stack_info is not None


@pytest.mark.skipif(sys.version_info < (3, 12), reason="replacement filters require Python 3.12")
def test_isolated_handler_forwards_replacement_records_through_filter_chains() -> None:
    target = _CollectingHandler()
    target.addFilter(_replace_message("target-safe"))  # type: ignore[arg-type]
    handler = IsolatedHandler(target)
    handler.addFilter(_replace_message("wrapper-safe"))  # type: ignore[arg-type]
    logger = logging.Logger("isolated.replacement", logging.INFO)
    logger.addHandler(handler)

    logger.info("REVIEWOPAQUE123456", extra={"invocation_id": "inv-1"})

    assert len(target.records) == 1
    assert target.records[0].getMessage() == "target-safe"
    assert target.records[0].__dict__["invocation_id"] == "inv-1"


def test_isolated_handler_rejects_false_filter_and_keeps_in_place_filter() -> None:
    target = _CollectingHandler()
    handler = IsolatedHandler(target)

    def mutate(record: logging.LogRecord) -> bool:
        record.msg = "mutated"
        return True

    handler.addFilter(mutate)
    handler.handle(logging.makeLogRecord({"msg": "original", "levelno": logging.INFO}))
    handler.addFilter(lambda _record: False)
    handler.handle(logging.makeLogRecord({"msg": "rejected", "levelno": logging.INFO}))

    assert [record.getMessage() for record in target.records] == ["mutated"]


def test_isolated_handler_flushes_without_owning_target_close() -> None:
    # Given
    target = _CollectingHandler()
    handler = IsolatedHandler(target)

    # When
    handler.flush()
    handler.close()

    # Then
    assert target.flush_count == 1
    assert target.close_count == 0


def test_isolated_handler_is_thread_safe() -> None:
    # Given
    logger, target, _ = _pipeline("isolated.threads", True)

    # When
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(lambda value: logger.info("thread", extra={"item": {"id": value}}), range(20))
        )

    # Then
    assert sorted(record.__dict__["item.id"] for record in target.records) == list(range(20))


def test_isolated_handler_is_async_task_safe() -> None:
    # Given
    logger, target, _ = _pipeline("isolated.async", True)

    async def emit(value: int) -> None:
        await anyio.lowlevel.checkpoint()
        logger.info("task", extra={"item": {"id": value}})

    async def run_tasks() -> None:
        async with anyio.create_task_group() as tasks:
            for value in range(20):
                tasks.start_soon(emit, value)

    # When
    anyio.run(run_tasks)

    # Then
    assert sorted(record.__dict__["item.id"] for record in target.records) == list(range(20))


def test_isolated_handler_bounds_deep_record_copy_without_raising() -> None:
    payload: dict[str, object] = {}
    tail = payload
    for _ in range(sys.getrecursionlimit() + 100):
        child: dict[str, object] = {}
        tail["next"] = child
        tail = child
    stream = io.StringIO()
    target = logging.StreamHandler(stream)
    target.setFormatter(JsonFormatter())
    logger = logging.Logger("isolated.deep-copy", logging.INFO)
    logger.addHandler(IsolatedHandler(target))

    logger.info("nested payload", extra={"payload": payload})

    assert json.loads(stream.getvalue())["extra"]["payload"]


def _wide_copy_fixture(count: int) -> tuple[logging.Logger, io.StringIO, dict[str, object]]:
    stream = io.StringIO()
    target = logging.StreamHandler(stream)
    target.setFormatter(JsonFormatter())
    logger = logging.Logger(f"isolated.wide-copy.{count}", logging.INFO)
    observed: dict[str, object] = {}

    def observe(record: logging.LogRecord) -> bool:
        observed["levelno"] = record.levelno
        observed["levelname"] = record.levelname
        return True

    handler = IsolatedHandler(target)
    handler.addFilter(observe)
    logger.addHandler(handler)
    return logger, stream, observed


@pytest.mark.parametrize("count", [4000, 4096, 4200])
def test_isolated_handler_preserves_level_metadata_with_wide_positional_args(count: int) -> None:
    """Regression (#580): a wide positional interpolation argument must not
    exhaust the shared copy budget before standard control fields (levelno,
    levelname) are copied -- a corrupted levelno previously raised TypeError
    during IsolatedHandler.emit()'s level comparison, below, at, and above
    the node budget."""
    logger, stream, observed = _wide_copy_fixture(count)

    logger.info("payload=%s", list(range(count)))

    assert observed["levelno"] == logging.INFO
    assert observed["levelname"] == "INFO"
    assert json.loads(stream.getvalue())["message"].startswith("payload=")


@pytest.mark.parametrize("count", [4000, 4096, 4200])
def test_isolated_handler_preserves_level_metadata_with_wide_mapping_args(count: int) -> None:
    """Regression (#580): a wide mapping (%-style dict) interpolation
    argument is passed as a bare dict (not wrapped in a tuple) -- the
    highest-risk shape for the top-level args value itself becoming the
    bare sentinel string once the budget is already exhausted."""
    logger, stream, observed = _wide_copy_fixture(count)
    mapping = {f"key{i}": i for i in range(count)}

    logger.info("payload=%(key0)s", mapping)

    assert observed["levelno"] == logging.INFO
    assert observed["levelname"] == "INFO"
    assert stream.getvalue()  # emitted, not raised


@pytest.mark.parametrize("count", [4000, 4200])
def test_isolated_handler_preserves_level_metadata_with_structured_message(count: int) -> None:
    """Regression (#580 acceptance): a structured message object (a dict
    passed as msg itself, not as an interpolation argument) must not corrupt
    control fields either."""
    logger, stream, observed = _wide_copy_fixture(count)

    logger.info({f"key{i}": i for i in range(count)})

    assert observed["levelno"] == logging.INFO
    assert observed["levelname"] == "INFO"
    assert stream.getvalue()


def test_isolated_handler_args_falls_back_to_empty_tuple_when_budget_already_exhausted() -> None:
    """Regression (#580): when a wide `msg` (processed before `args` in
    LogRecord's own field order) exhausts the budget first, `args` itself
    -- not just a nested item inside it -- would become the bare sentinel
    *string* in place of a tuple. Confirm the documented empty-tuple
    fallback actually engages here, and that the resulting record still
    renders and emits without raising.

    Uses nested containers (not scalars) to exhaust the node budget: only
    dict/list/tuple nodes consume it, so a flat structure of 5,000 plain
    ints would not -- copying a scalar is O(1) and carries no recursion
    risk, unlike recursing into 5,000 separate container nodes."""
    logger, stream, observed = _wide_copy_fixture(5000)

    logger.info({f"key{i}": [] for i in range(5000)}, "wasted_positional_arg")

    assert observed["levelno"] == logging.INFO
    assert observed["levelname"] == "INFO"
    assert stream.getvalue()  # emitted without raising


@pytest.mark.parametrize("count", [4000, 4200])
def test_isolated_handler_preserves_level_metadata_with_wide_extra(count: int) -> None:
    """Regression (#580 acceptance): the existing wide-extra path (not just
    args) must also leave control fields uncorrupted."""
    logger, stream, observed = _wide_copy_fixture(count)

    logger.info("payload", extra={"items": list(range(count))})

    assert observed["levelno"] == logging.INFO
    assert observed["levelname"] == "INFO"
    assert stream.getvalue()


def test_isolated_handler_truncated_args_do_not_break_interpolation() -> None:
    """Regression (#580): when the budget is already exhausted before args
    is reached, args falls back to an empty tuple rather than the bare
    sentinel string, so %-interpolation with a multi-placeholder format
    string never raises -- even though the message renders unsubstituted."""
    stream = io.StringIO()
    target = logging.StreamHandler(stream)
    target.setFormatter(JsonFormatter())
    logger = logging.Logger("isolated.wide-copy.multi-placeholder", logging.INFO)
    logger.addHandler(IsolatedHandler(target))

    # A large extra consumes the whole budget before args is even reached
    # (extra follows args/msg in the iteration order fixed by #580, but a
    # second, even larger extra value after it still forces exhaustion by
    # the time any remaining fields are processed).
    logger.info(
        "multi %s %s placeholder",
        "first",
        "second",
        extra={"filler": list(range(5000))},
    )

    assert stream.getvalue()  # emitted without raising


def test_isolated_handler_preserves_exception_info_with_wide_sibling_extra() -> None:
    """Regression (#580 acceptance): exception handling metadata (exc_info)
    must survive a wide sibling extra field exhausting the budget."""
    stream = io.StringIO()
    target = logging.StreamHandler(stream)
    target.setFormatter(JsonFormatter())
    logger = logging.Logger("isolated.wide-copy.exc-info", logging.INFO)
    logger.addHandler(IsolatedHandler(target))

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed", extra={"items": list(range(5000))})

    payload = json.loads(stream.getvalue())
    assert "ValueError: boom" in payload["exception"]
