"""bind_context: scoped request fields for plain stdlib loggers."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import contextvars
import io
import json
import logging

import pytest

from azure_functions_logging import (
    FunctionLogger,
    JsonFormatter,
    bind_context,
    logging_context,
    propagate_context,
    reset_context,
    setup_logging,
)
from azure_functions_logging._context import (
    ContextFilter,
    _install_context_factory,
    _uninstall_context_factory,
    bound_context_var,
)


class _Ctx:
    invocation_id = "inv-bind"
    function_name = "bind_fn"
    trace_context = None


@pytest.fixture
def sink() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    logger = logging.getLogger("bind.test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield logger, stream
    logger.handlers = []
    reset_context()


def _records(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def _extra(record: dict[str, object]) -> dict[str, object]:
    extra = record.get("extra")
    assert isinstance(extra, dict)
    return extra


def test_plain_logger_gets_bound_fields_and_they_are_restored(
    sink: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = sink
    with bind_context(order_id="A-42", tenant="demo"):
        logger.info("started")
    logger.info("after")
    first, second = _records(stream)
    assert _extra(first) == {"order_id": "A-42", "tenant": "demo"}
    assert "order_id" not in second.get("extra", {})  # type: ignore[operator]


def test_nested_bindings_override_then_restore(sink: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = sink
    with bind_context(a=1, b=1):
        with bind_context(b=2, c=3):
            logger.info("inner")
        logger.info("outer")
    inner, outer = _records(stream)
    assert _extra(inner) == {"a": 1, "b": 2, "c": 3}
    assert _extra(outer) == {"a": 1, "b": 1}
    assert bound_context_var.get() == {}


def test_bindings_are_restored_when_body_raises(sink: tuple[logging.Logger, io.StringIO]) -> None:
    with pytest.raises(RuntimeError):
        with bind_context(k="v"):
            raise RuntimeError("boom")
    assert bound_context_var.get() == {}


def test_empty_bind_is_a_noop(sink: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = sink
    with bind_context():
        logger.info("x")
    assert "order_id" not in stream.getvalue()


def test_combines_with_invocation_context(sink: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = sink
    with logging_context(_Ctx()), bind_context(order_id="A-1"):
        logger.info("both")
    (rec,) = _records(stream)
    assert rec["invocation_id"] == "inv-bind"
    assert _extra(rec)["order_id"] == "A-1"


@pytest.mark.parametrize("key", ["name", "message", "levelname", "invocation_id", "trace_id"])
def test_reserved_keys_are_renamed_not_lost_and_never_raise(
    sink: tuple[logging.Logger, io.StringIO], key: str
) -> None:
    logger, stream = sink
    with bind_context(**{key: "value"}):
        logger.info("reserved %s", key)
    (rec,) = _records(stream)
    assert _extra(rec)[f"extra_{key}"] == "value"
    assert rec.get(key) != "value"


def test_explicit_extra_wins_over_bound_value(sink: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = sink
    with bind_context(order_id="bound"):
        logger.info("x", extra={"order_id": "explicit"})
    (rec,) = _records(stream)
    assert _extra(rec)["order_id"] == "explicit"


def test_function_logger_bind_wins_and_mixed_loggers_share_bindings(
    sink: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = sink
    wrapped = FunctionLogger(logger).bind(order_id="wrapper")
    with bind_context(order_id="bound", tenant="t"):
        logger.info("plain")
        wrapped.info("wrapped")
    plain, wrap = _records(stream)
    assert _extra(plain) == {"order_id": "bound", "tenant": "t"}
    assert _extra(wrap) == {"order_id": "wrapper", "tenant": "t"}


def test_function_logger_bind_remains_immutable_and_clear_context_mutates_receiver() -> None:
    base = FunctionLogger(logging.getLogger("bind.immut"))
    child = base.bind(a=1)
    assert base._context == {} and child._context == {"a": 1}
    child.clear_context()
    assert child._context == {}


def test_parallel_asyncio_tasks_are_isolated(sink: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = sink

    async def worker(name: str) -> None:
        with bind_context(worker=name):
            await asyncio.sleep(0)
            logger.info("work %s", name)
            await asyncio.sleep(0)

    async def main() -> None:
        await asyncio.gather(*(worker(f"w{i}") for i in range(5)))

    asyncio.run(main())
    for rec in _records(stream):
        assert _extra(rec)["worker"] == str(rec["message"]).split()[-1]


def test_threads_do_not_inherit_but_propagate_context_carries_bindings(
    sink: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = sink

    def work(label: str) -> None:
        logger.info(label)

    with bind_context(order_id="T-1"), ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(work, "plain-thread").result()
        pool.submit(propagate_context(work), "propagated").result()
    plain, propagated = _records(stream)
    assert "order_id" not in plain.get("extra", {})  # type: ignore[operator]
    assert _extra(propagated)["order_id"] == "T-1"


def test_concurrent_invocations_do_not_leak(sink: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = sink

    def invocation(i: int) -> None:
        with bind_context(req=i):
            logger.info("r%s", i)

    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: ctx.copy().run(invocation, i), range(20)))
    for rec in _records(stream):
        assert _extra(rec)["req"] == int(str(rec["message"])[1:])


def test_record_factory_strategy_and_explicit_extra_collision() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("bind.factory")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    previous = logging.getLogRecordFactory()
    _install_context_factory(None)
    try:
        with bind_context(order_id="bound", tenant="t"):
            logger.info("plain")
            logger.info("override", extra={"order_id": "explicit"})  # must not raise KeyError
    finally:
        _uninstall_context_factory()
        logging.setLogRecordFactory(previous)
        logger.handlers = []
    plain, override = _records(stream)
    assert _extra(plain) == {"order_id": "bound", "tenant": "t"}
    assert _extra(override)["order_id"] == "explicit"


def test_setup_logging_extra_context_vars_name_wins_over_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_var", default="from-var")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter({"tenant": var}))
    logger = logging.getLogger("bind.extra_vars")
    logger.handlers = [handler]
    logger.propagate = False
    try:
        with bind_context(tenant="bound"):
            logger.warning("x")
    finally:
        logger.handlers = []
    (rec,) = _records(stream)
    assert _extra(rec)["tenant"] == "from-var"


def test_raw_unconfigured_handler_does_not_receive_bound_fields() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)  # no ContextFilter, no factory
    handler.setFormatter(logging.Formatter("%(message)s|%(order_id)s"))
    logger = logging.getLogger("bind.raw")
    logger.handlers = [handler]
    logger.propagate = False
    try:
        with bind_context(order_id="A-9"):
            logger.warning("x")
    finally:
        logger.handlers = []
    assert "A-9" not in stream.getvalue()  # documented: no guaranteed injection


def test_reset_context_clears_bindings() -> None:
    token = bound_context_var.set({"k": "v"})
    try:
        reset_context()
        assert bound_context_var.get() == {}
    finally:
        bound_context_var.reset(token)


def test_setup_logging_integration_with_plain_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FUNCTIONS_WORKER_RUNTIME", raising=False)
    import azure_functions_logging._setup as setup_mod

    setup_mod._configured_loggers.clear()
    stream = io.StringIO()
    setup_logging(logger_name="bind.local", format="json")
    logger = logging.getLogger("bind.local")
    stream_handler = logger.handlers[0]
    assert isinstance(stream_handler, logging.StreamHandler)
    stream_handler.setStream(stream)
    try:
        with bind_context(order_id="A-1"):
            logging.getLogger("bind.local").info("hello")
    finally:
        logger.handlers = []
        setup_mod._configured_loggers.clear()
        logger.propagate = True
    (rec,) = _records(stream)
    assert _extra(rec)["order_id"] == "A-1"
