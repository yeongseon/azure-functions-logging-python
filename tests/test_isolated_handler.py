from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextvars import Context, copy_context
import io
import json
import logging
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


def test_isolated_handler_preserves_tuple_list_cycle() -> None:
    # Given
    logger, target, _ = _pipeline("isolated.tuple-cycle", True)
    child: list[tuple[object, ...]] = []
    cycle: tuple[object, ...] = (child,)
    child.append(cycle)

    # When
    logger.info("cycle", extra={"cycle": cycle})

    # Then
    cloned_cycle = target.records[0].__dict__["cycle"]
    assert cloned_cycle is cloned_cycle[0][0]


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
