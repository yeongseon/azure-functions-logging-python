from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import io
import json
import logging
from types import SimpleNamespace

import pytest

from azure_functions_logging import JsonFormatter, logging_context, setup_logging
from azure_functions_logging._context import ContextFilter
import azure_functions_logging._setup as setup_mod


@pytest.fixture(autouse=True)
def isolated_setup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    factory = logging.getLogRecordFactory()
    root = logging.getLogger()
    handlers, filters = root.handlers[:], root.filters[:]
    root.handlers = [logging.NullHandler()]
    root.filters = []
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()
    setup_mod._owned_factory = None
    monkeypatch.setenv("FUNCTIONS_WORKER_RUNTIME", "python")
    yield
    root.handlers, root.filters = handlers, filters
    logging.setLogRecordFactory(factory)
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()


def test_repeated_filter_setup_recovers_late_host_handler() -> None:
    setup_logging()
    late = logging.NullHandler()
    logging.getLogger().addHandler(late)
    setup_logging()
    setup_logging()
    assert sum(type(f) is ContextFilter for f in late.filters) == 1


def test_factory_setup_preserves_previous_factory_and_removes_root_filters() -> None:
    previous = logging.getLogRecordFactory()
    setup_logging()
    setup_logging(use_record_factory=True)
    active = logging.getLogRecordFactory()
    setup_logging(use_record_factory=True)
    assert logging.getLogRecordFactory() is active
    assert active is not previous
    assert not any(type(f) is ContextFilter for f in logging.getLogger().filters)


def test_switch_back_restores_previous_factory_and_filter_mode() -> None:
    previous = logging.getLogRecordFactory()
    setup_logging(use_record_factory=True)
    setup_logging(use_record_factory=False)
    assert logging.getLogRecordFactory() is previous
    assert sum(type(f) is ContextFilter for f in logging.getLogger().handlers[0].filters) == 1


def test_factory_upgrade_removes_filters_from_other_configured_loggers() -> None:
    named = logging.getLogger("strategy.other")
    handler = logging.NullHandler()
    named.addHandler(handler)
    handler.addFilter(ContextFilter())
    try:
        setup_logging(use_record_factory=True)
        assert not any(type(f) is ContextFilter for f in handler.filters)
    finally:
        named.removeHandler(handler)


def test_switch_rejects_third_party_wrapper_without_uninstalling_it() -> None:
    setup_logging(use_record_factory=True)
    owned = logging.getLogRecordFactory()

    def foreign(*args: object, **kwargs: object) -> logging.LogRecord:
        return owned(*args, **kwargs)

    logging.setLogRecordFactory(foreign)
    with pytest.raises(RuntimeError, match="restore the package-owned factory"):
        setup_logging(use_record_factory=False)
    assert logging.getLogRecordFactory() is foreign


def test_switch_back_restores_foreign_predecessor_with_custom_fields() -> None:
    baseline = logging.getLogRecordFactory()

    def predecessor(*args: object, **kwargs: object) -> logging.LogRecord:
        record = baseline(*args, **kwargs)
        record.__dict__["foreign"] = "preserved"
        return record

    logging.setLogRecordFactory(predecessor)
    setup_logging(use_record_factory=True)
    setup_logging()
    assert logging.getLogRecordFactory() is predecessor
    assert logging.makeLogRecord({}).__dict__["foreign"] == "preserved"


@pytest.mark.parametrize("factory_mode", [False, True])
def test_concurrent_invocations_and_outside_records_are_isolated(factory_mode: bool) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    setup_logging(use_record_factory=factory_mode)
    logger = logging.getLogger("strategy.concurrent.thirdparty")

    def emit(index: int) -> None:
        context = SimpleNamespace(invocation_id=f"inv-{index}", function_name="parallel")
        with logging_context(context):
            logger.warning("inside", extra={"index": index})
        logger.warning("outside")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(emit, range(16)))

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 32
    for record in records:
        if record["message"] == "inside":
            assert record["invocation_id"] == f"inv-{record['extra']['index']}"
        else:
            assert record["invocation_id"] is None


def test_local_strategy_roundtrip_recovers_same_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FUNCTIONS_WORKER_RUNTIME")
    logger = logging.getLogger("strategy.local")
    handler = logging.StreamHandler(io.StringIO())
    logger.addHandler(handler)
    try:
        setup_logging(logger_name=logger.name)
        setup_logging(logger_name=logger.name, use_record_factory=True)
        assert not any(type(f) is ContextFilter for f in handler.filters)
        setup_logging(logger_name=logger.name)
        assert sum(type(f) is ContextFilter for f in handler.filters) == 1
        assert logger.handlers == [handler]
    finally:
        logger.removeHandler(handler)
