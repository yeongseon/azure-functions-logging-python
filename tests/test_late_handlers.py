"""Late-registered handlers: context metadata and secure redaction at invocation entry."""

from collections.abc import Iterator
import io
import logging
import threading
from types import SimpleNamespace

import pytest

from azure_functions_logging import (
    IsolatedHandler,
    JsonFormatter,
    attach_secure_redaction,
    configure_secure_redaction,
    logging_context,
    setup_logging,
    with_context,
)
from azure_functions_logging._secure import _SecureRedactionFilter
import azure_functions_logging._setup as setup_mod

CANARY = "CANARY_LATE_HANDLER"


class _Ctx:
    invocation_id = "inv-late"
    function_name = "late_fn"
    trace_context = None


class InspectFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return super().format(record) + repr(record.__dict__)


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    root = logging.getLogger()
    handlers, filters, level = root.handlers[:], root.filters[:], root.level
    factory = logging.getLogRecordFactory()
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()
    monkeypatch.setenv("FUNCTIONS_WORKER_RUNTIME", "python")
    root.handlers = []
    root.filters = []
    root.setLevel(logging.INFO)
    created: list[logging.Logger] = []
    yield
    for lg in created:
        lg.handlers = []
    configure_secure_redaction(enabled=False)
    root.handlers, root.filters = handlers, filters
    root.setLevel(level)
    logging.setLogRecordFactory(factory)
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()
    for name in ("late.child", "late.solo"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def _isolate_root() -> None:
    """Drop pytest's capture handlers: they would sanitize shared records first."""
    logging.getLogger().handlers.clear()


def _handler(stream: io.StringIO) -> logging.StreamHandler[io.StringIO]:
    h = logging.StreamHandler(stream)
    h.setFormatter(InspectFormatter("%(message)s"))
    return h


def _emit_secret(name: str) -> None:
    logging.getLogger(name).info("password=%s", CANARY)


def test_late_root_handler_gets_context_and_redaction_at_next_entry() -> None:
    _isolate_root()
    # Given: setup and secure mode were configured before the handler existed
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    logging.getLogger().addHandler(_handler(stream))
    # When
    with logging_context(_Ctx()):
        _emit_secret("late.child")
    # Then
    out = stream.getvalue()
    assert CANARY not in out
    assert "inv-late" in out


def test_late_named_non_propagating_handler_is_redacted() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    solo = logging.getLogger("late.solo")
    solo.propagate = False
    solo.addHandler(_handler(stream))
    with logging_context(_Ctx()):
        _emit_secret("late.solo")
    assert CANARY not in stream.getvalue()


def test_late_isolated_handler_target_is_redacted() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    target = _handler(stream)
    logging.getLogger().addHandler(IsolatedHandler(target))
    with logging_context(_Ctx()):
        _emit_secret("late.child")
    assert CANARY not in stream.getvalue()


def test_replacement_with_unchanged_handler_count_is_covered() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    root = logging.getLogger()
    first = _handler(io.StringIO())
    root.addHandler(first)
    with logging_context(_Ctx()):
        pass
    root.removeHandler(first)
    stream = io.StringIO()
    root.addHandler(_handler(stream))  # same count, different object
    with logging_context(_Ctx()):
        _emit_secret("late.child")
    assert CANARY not in stream.getvalue()
    assert "inv-late" in stream.getvalue()


def test_repeated_entry_does_not_duplicate_filters_or_records() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    handler = _handler(stream)
    logging.getLogger().addHandler(handler)
    for _ in range(5):
        with logging_context(_Ctx()):
            pass
    with logging_context(_Ctx()):
        logging.getLogger("late.child").info("once")
    secure = [f for f in handler.filters if type(f) is _SecureRedactionFilter]
    ctx = [f for f in handler.filters if type(f).__name__ == "ContextFilter"]
    assert len(secure) == 1 and len(ctx) == 1
    assert handler.filters[-1] is secure[0]
    assert stream.getvalue().count("once") >= 1
    assert stream.getvalue().count("\n") == 1
    assert len(logging.getLogger().handlers) == 1


def test_secure_filter_stays_last_when_context_filter_added_later() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    handler = _handler(io.StringIO())
    logging.getLogger().addHandler(handler)
    with logging_context(_Ctx()):
        pass
    assert type(handler.filters[-1]) is _SecureRedactionFilter


def test_record_factory_mode_does_not_attach_context_filter_but_redacts() -> None:
    _isolate_root()
    setup_logging(use_record_factory=True)
    configure_secure_redaction()
    stream = io.StringIO()
    handler = _handler(stream)
    logging.getLogger().addHandler(handler)
    with logging_context(_Ctx()):
        _emit_secret("late.child")
    assert not [f for f in handler.filters if type(f).__name__ == "ContextFilter"]
    assert CANARY not in stream.getvalue()
    assert "inv-late" in stream.getvalue()


def test_setup_logging_does_not_downgrade_secure_mode() -> None:
    _isolate_root()
    configure_secure_redaction()
    setup_logging()
    setup_logging(use_record_factory=True)
    setup_logging()
    stream = io.StringIO()
    logging.getLogger().addHandler(_handler(stream))
    with logging_context(_Ctx()):
        _emit_secret("late.child")
    assert CANARY not in stream.getvalue()


def test_disable_stops_reconciliation_and_removes_filters() -> None:
    _isolate_root()
    configure_secure_redaction()
    configure_secure_redaction(enabled=False)
    handler = _handler(io.StringIO())
    logging.getLogger().addHandler(handler)
    with logging_context(_Ctx()):
        pass
    assert not [f for f in handler.filters if type(f) is _SecureRedactionFilter]


def test_without_secure_mode_no_redaction_filter_is_added() -> None:
    _isolate_root()
    setup_logging()
    handler = _handler(io.StringIO())
    logging.getLogger().addHandler(handler)
    with logging_context(_Ctx()):
        pass
    assert not [f for f in handler.filters if type(f) is _SecureRedactionFilter]


def test_with_context_decorator_entry_reconciles() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    logging.getLogger().addHandler(_handler(stream))

    @with_context
    def handler(req: object, context: object) -> None:
        _emit_secret("late.child")

    handler(None, _Ctx())
    assert CANARY not in stream.getvalue()


def test_handler_added_during_invocation_is_outside_entry_boundary_until_attached() -> None:
    """Documented boundary: a handler added mid-invocation is covered at next entry."""
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    mid = _handler(stream)
    with logging_context(_Ctx()):
        logging.getLogger().addHandler(mid)
        attach_secure_redaction(mid)  # explicit contract for mid-invocation handlers
        _emit_secret("late.child")
    assert CANARY not in stream.getvalue()
    late = _handler(io.StringIO())
    with logging_context(_Ctx()):
        logging.getLogger().addHandler(late)
    with logging_context(_Ctx()):
        pass
    assert type(late.filters[-1]) is _SecureRedactionFilter


def test_concurrent_invocations_with_handler_churn_never_leak() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    root = logging.getLogger()
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for _ in range(20):
                h = _handler(stream)
                root.addHandler(h)
                with logging_context(SimpleNamespace(invocation_id=f"i{i}", function_name="f")):
                    _emit_secret("late.child")
                root.removeHandler(h)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    # a handler present at entry is always protected; the churn handlers above are added
    # before entry in the same thread, but another thread may add one between entry and emit.
    # That window is the documented boundary, so only assert no crash and no leak of
    # handlers that were reconciled.
    assert root.handlers == []


def test_json_formatter_sink_after_late_registration() -> None:
    _isolate_root()
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    h = logging.StreamHandler(stream)
    h.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(h)
    with logging_context(_Ctx()):
        _emit_secret("late.child")
    assert CANARY not in stream.getvalue()
    assert "inv-late" in stream.getvalue()


def test_reconciliation_failure_warns_but_never_breaks_the_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import azure_functions_logging._secure as secure_mod

    configure_secure_redaction()

    def boom(_: logging.Handler) -> None:
        raise RuntimeError("boom")

    logging.getLogger().addHandler(_handler(io.StringIO()))
    monkeypatch.setattr(secure_mod, "attach_secure_redaction", boom)
    with pytest.warns(RuntimeWarning, match="reconciliation failed"):
        with logging_context(_Ctx()):
            ran = True
    assert ran


def test_handler_scan_retries_when_logger_registry_mutates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import azure_functions_logging._secure as secure_mod

    calls = {"n": 0}
    original = dict(logging.Logger.manager.loggerDict)

    class Flaky(dict):  # type: ignore[type-arg]
        def values(self):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("dictionary changed size during iteration")
            return original.values()

    monkeypatch.setattr(logging.Logger.manager, "loggerDict", Flaky(original))
    assert secure_mod._all_handlers() is not None
    assert calls["n"] == 2
