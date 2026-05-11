from __future__ import annotations

from collections.abc import Iterator
import logging
import os
from unittest.mock import patch

import pytest

from azure_functions_logging._context import ContextFilter
from azure_functions_logging._formatter import ColorFormatter
import azure_functions_logging._setup as setup_mod
from azure_functions_logging._setup import (
    _is_azure_hosted,
    _is_functions_environment,
    setup_logging,
)


@pytest.fixture(autouse=True)
def reset_setup_state() -> Iterator[None]:
    setup_mod._configured_loggers.clear()
    saved_factory = logging.getLogRecordFactory()
    yield
    logging.setLogRecordFactory(saved_factory)
    setup_mod._configured_loggers.clear()


def test_setup_logging_local_dev_adds_handler_with_color_formatter() -> None:
    logger_name = "afl.test.local"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, level=logging.DEBUG)

    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, ColorFormatter)

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_azure_env_adds_only_filter() -> None:
    root = logging.getLogger()
    root.filters.clear()
    test_handler = logging.StreamHandler()
    root.handlers = [test_handler]

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        setup_logging()

    assert root.handlers == [test_handler]
    assert any(isinstance(flt, ContextFilter) for flt in root.filters)
    assert any(isinstance(flt, ContextFilter) for flt in test_handler.filters)

    root.handlers = []
    root.filters.clear()


def test_setup_logging_is_idempotent() -> None:
    logger_name = "afl.test.idempotent"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name)
        first_handlers = list(logger.handlers)
        setup_logging(logger_name=logger_name)

    assert logger.handlers == first_handlers

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_is_idempotent_per_logger_name() -> None:
    first_name = "afl.test.idempotent.first"
    second_name = "afl.test.idempotent.second"
    first = logging.getLogger(first_name)
    second = logging.getLogger(second_name)
    first.handlers.clear()
    first.filters.clear()
    second.handlers.clear()
    second.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=first_name)
        setup_logging(logger_name=second_name)

    assert len(first.handlers) == 1
    assert len(second.handlers) == 1

    first.handlers.clear()
    first.filters.clear()
    second.handlers.clear()
    second.filters.clear()


def test_is_functions_environment() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert _is_functions_environment() is False
    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        assert _is_functions_environment() is True


def test_is_azure_hosted() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert _is_azure_hosted() is False
    with patch.dict(os.environ, {"WEBSITE_INSTANCE_ID": "abc123"}, clear=True):
        assert _is_azure_hosted() is True


def test_setup_logging_functions_formatter_applied_in_azure_env() -> None:
    root = logging.getLogger()
    root.filters.clear()
    test_handler = logging.StreamHandler()
    root.handlers = [test_handler]
    custom_formatter = logging.Formatter("%(message)s")

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        setup_logging(functions_formatter=custom_formatter)

    assert test_handler.formatter is custom_formatter

    root.handlers = []
    root.filters.clear()


def test_setup_logging_in_azure_env_does_not_install_duplicate_context_filters() -> None:
    root = logging.getLogger()
    root.handlers = [logging.StreamHandler()]
    root.filters.clear()

    import azure_functions_logging._setup as setup_mod

    setup_mod._configured_loggers.clear()

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        setup_logging()
        setup_logging()

    handler = root.handlers[0]
    context_filters_on_handler = [f for f in handler.filters if isinstance(f, ContextFilter)]
    context_filters_on_root = [f for f in root.filters if isinstance(f, ContextFilter)]

    assert len(context_filters_on_handler) == 1
    assert len(context_filters_on_root) == 1

    root.handlers = []
    root.filters.clear()


def test_is_functions_environment_with_only_website_instance_id_is_false() -> None:
    with patch.dict(os.environ, {"WEBSITE_INSTANCE_ID": "abc123"}, clear=True):
        assert _is_functions_environment() is False
        assert _is_azure_hosted() is True


def test_format_json_warns_in_azure_environment() -> None:
    """When format='json' and no functions_formatter in Azure, emit a warning."""
    import warnings

    root = logging.getLogger()
    root.handlers = [logging.StreamHandler()]

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging(format="json")

        assert len(w) == 1
        assert "format" in str(w[0].message).lower()
        assert "ignored" in str(w[0].message).lower()

    root.handlers = []
    root.filters.clear()


def test_format_color_no_warning_in_azure_environment() -> None:
    """When format='color' (default) in Azure, no warning."""
    import warnings

    root = logging.getLogger()
    root.handlers = [logging.StreamHandler()]

    with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging(format="color")

        assert len(w) == 0

    root.handlers = []
    root.filters.clear()


def test_setup_logging_use_record_factory_installs_factory() -> None:
    """use_record_factory=True installs the global LogRecordFactory."""
    from azure_functions_logging._context import (
        _CONTEXT_FACTORY_MARKER,
    )

    logger_name = "afl.test.use_record_factory"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    baseline_factory = logging.getLogRecordFactory()
    assert not getattr(baseline_factory, _CONTEXT_FACTORY_MARKER, False)

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, use_record_factory=True)

    active_factory = logging.getLogRecordFactory()
    assert getattr(active_factory, _CONTEXT_FACTORY_MARKER, False) is True

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_use_record_factory_default_false_does_not_install() -> None:
    """Default behavior must not touch the global LogRecordFactory."""
    from azure_functions_logging._context import (
        _CONTEXT_FACTORY_MARKER,
    )

    logger_name = "afl.test.no_record_factory"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name)

    active_factory = logging.getLogRecordFactory()
    assert not getattr(active_factory, _CONTEXT_FACTORY_MARKER, False)

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_use_record_factory_is_idempotent() -> None:
    """Repeated setup_logging(use_record_factory=True) keeps a single factory."""
    from azure_functions_logging._context import (
        _CONTEXT_FACTORY_MARKER,
    )

    first_name = "afl.test.factory.first"
    second_name = "afl.test.factory.second"
    for name in (first_name, second_name):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=first_name, use_record_factory=True)
        first_factory = logging.getLogRecordFactory()
        setup_logging(logger_name=second_name, use_record_factory=True)
        second_factory = logging.getLogRecordFactory()

    assert first_factory is second_factory
    assert getattr(second_factory, _CONTEXT_FACTORY_MARKER, False) is True

    for name in (first_name, second_name):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.filters.clear()


def test_setup_logging_use_record_factory_skips_context_filter() -> None:
    """With use_record_factory=True, ContextFilter must NOT be attached.

    Otherwise the filter would overwrite factory-injected fields with current
    contextvar values at handler dispatch time, defeating the record-creation-
    time guarantee under queued / cross-thread / delayed handling.
    """
    logger_name = "afl.test.factory.no_filter"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, use_record_factory=True)

    assert not any(isinstance(f, ContextFilter) for f in logger.filters)
    for handler in logger.handlers:
        assert not any(isinstance(f, ContextFilter) for f in handler.filters)

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_factory_record_survives_contextvar_reset() -> None:
    """Regression: factory-injected fields must survive contextvar reset.

    Simulates queued/delayed handling: a record is created inside a context,
    then the context is reset before the handler runs. With use_record_factory,
    the snapshot must be preserved (no ContextFilter to overwrite it).
    """
    from azure_functions_logging._context import invocation_id_var

    logger_name = "afl.test.factory.snapshot"
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, use_record_factory=True)

    token = invocation_id_var.set("test-invocation-123")
    try:
        record = logger.makeRecord(
            logger_name, logging.INFO, "f.py", 1, "msg", (), None,
        )
    finally:
        invocation_id_var.reset(token)

    # Context reset — but record was already created.
    invocation_id_var.set(None)

    # Run any handler filters (there should be none, but if any existed
    # they must not overwrite the snapshot).
    for handler in logger.handlers:
        for flt in handler.filters:
            if isinstance(flt, logging.Filter):
                flt.filter(record)

    assert getattr(record, "invocation_id", None) == "test-invocation-123"

    logger.handlers.clear()
    logger.filters.clear()


def test_setup_logging_invalid_format_leaves_no_global_side_effects() -> None:
    """Invalid `format` must raise BEFORE any global side effects (e.g. factory)."""
    baseline_factory = logging.getLogRecordFactory()

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="format must be"):
            setup_logging(format="bogus", use_record_factory=True)

    # Factory must not have been swapped despite use_record_factory=True
    assert logging.getLogRecordFactory() is baseline_factory
