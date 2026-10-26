"""Secure profile installation and real downstream formatter contracts."""

from collections.abc import Iterator
import contextvars
import io
import logging

import pytest

import azure_functions_logging as afl
from azure_functions_logging import (
    AttributeFlattenFilter,
    JsonFormatter,
    configure_secure_redaction,
    setup_logging,
)
from azure_functions_logging._formatter import ColorFormatter
from azure_functions_logging._secure import _SecureRedactionFilter
import azure_functions_logging._setup as setup_mod

CANARY = "CANARY_SECRET_PROFILE"


@pytest.fixture(autouse=True)
def clean_setup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    root = logging.getLogger()
    handlers, filters, level = root.handlers[:], root.filters[:], root.level
    factory = logging.getLogRecordFactory()
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()
    monkeypatch.setenv("FUNCTIONS_WORKER_RUNTIME", "python")
    root.handlers = []
    root.filters = []
    root.setLevel(logging.INFO)
    yield
    root.handlers, root.filters = handlers, filters
    root.setLevel(level)
    logging.setLogRecordFactory(factory)
    setup_mod._configured_loggers.clear()
    setup_mod._azure_state.clear()


class InspectFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return super().format(record) + repr(record.__dict__)


@pytest.mark.parametrize("formatter", [ColorFormatter(), JsonFormatter(), InspectFormatter()])
def test_child_records_are_masked_before_every_formatter(formatter: logging.Formatter) -> None:
    # Given
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)
    setup_logging()
    configure_secure_redaction()
    # When
    try:
        raise ValueError(f"password={CANARY}")
    except ValueError:
        logging.getLogger("secure.child").exception(
            "Bearer %s", CANARY, extra={"headers": {"Proxy-Authorization": CANARY}}
        )
    # Then
    output = stream.getvalue()
    assert CANARY not in output
    assert "***" in output
    assert "ValueError" in output


def test_secure_runs_after_injected_context_and_flattening() -> None:
    # Given
    context: contextvars.ContextVar[str] = contextvars.ContextVar(
        "secure_note", default=f"token={CANARY}"
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(InspectFormatter())
    handler.addFilter(AttributeFlattenFilter())
    logging.getLogger().addHandler(handler)
    # When
    setup_logging(extra_context_vars={"note": context})
    configure_secure_redaction()
    logging.getLogger("secure.order.child").warning(
        "ordinary", extra={"payload": {"token": CANARY}}
    )
    # Then
    assert CANARY not in stream.getvalue()
    assert "note" in stream.getvalue()


def test_secure_reconfiguration_is_idempotent_and_off_preserves_user_filters() -> None:
    # Given
    handler = logging.StreamHandler(io.StringIO())
    logging.getLogger().addHandler(handler)
    setup_logging()
    configure_secure_redaction()
    original = tuple(handler.filters)
    # When
    configure_secure_redaction()
    # Then
    assert tuple(handler.filters) == original
    owned = handler.filters[-1]

    class UserFilter(_SecureRedactionFilter):
        pass

    user = UserFilter()
    handler.addFilter(user)
    configure_secure_redaction(enabled=False)
    assert owned not in handler.filters
    assert user in handler.filters


def test_late_handler_can_be_protected_before_registration() -> None:
    # Given
    setup_logging()
    configure_secure_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    # When
    afl.attach_secure_redaction(handler)
    afl.attach_secure_redaction(handler)
    logging.getLogger().addHandler(handler)
    logging.getLogger("secure.late").warning("token=%s", CANARY)
    # Then
    assert CANARY not in stream.getvalue()
    assert len(handler.filters) == 1


def test_local_repeat_call_protects_new_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.delenv("FUNCTIONS_WORKER_RUNTIME")
    setup_logging(logger_name="secure.local")
    configure_secure_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    # When
    setup_logging(logger_name="secure.local")
    configure_secure_redaction()
    logging.getLogger("secure.other").warning("Bearer %s", CANARY)
    # Then
    assert CANARY not in stream.getvalue()
    logging.getLogger("secure.local").handlers.clear()


def test_ordinary_setup_preserves_explicit_secure_policy() -> None:
    # Given
    stream = io.StringIO()
    logging.getLogger().addHandler(logging.StreamHandler(stream))
    configure_secure_redaction()
    # When
    setup_logging()
    logging.getLogger("secure.preserved").warning("token=%s", CANARY)
    # Then
    assert CANARY not in stream.getvalue()
