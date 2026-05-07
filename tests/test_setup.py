from __future__ import annotations

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
def reset_setup_state() -> None:
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
