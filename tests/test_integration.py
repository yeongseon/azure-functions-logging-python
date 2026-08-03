from __future__ import annotations

import io
import logging
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import azure_functions_logging as afl
from azure_functions_logging import (
    FunctionLogger,
    JsonFormatter,
    get_logger,
    inject_context,
    setup_logging,
)
import azure_functions_logging._context as ctx_mod
from azure_functions_logging._context import (
    cold_start_var,
    function_name_var,
    invocation_id_var,
    trace_id_var,
)
import azure_functions_logging._setup as setup_mod


@pytest.fixture(autouse=True)
def reset_state() -> None:
    setup_mod._configured_loggers.clear()
    ctx_mod._cold_start = True
    invocation_id_var.set(None)
    function_name_var.set(None)
    trace_id_var.set(None)
    cold_start_var.set(None)


def test_full_flow_logs_with_injected_context() -> None:
    logger_name = "afl.integration"
    target = logging.getLogger(logger_name)
    target.handlers.clear()
    target.filters.clear()

    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name)

    stream = io.StringIO()
    handler = target.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)

    logger = get_logger(logger_name)
    context = SimpleNamespace(
        invocation_id="inv-int",
        function_name="fn-int",
        trace_context=SimpleNamespace(
            trace_parent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
        ),
    )
    inject_context(context)

    logger.info("integration message")

    output = stream.getvalue()
    assert "integration message" in output
    assert "invocation_id=inv-int" in output
    assert "function_name=fn-int" in output
    assert "trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in output
    assert "cold_start=true" in output

    target.handlers.clear()
    target.filters.clear()


def test_get_logger_returns_function_logger() -> None:
    logger = get_logger("afl.integration.type")
    assert isinstance(logger, FunctionLogger)


def test_public_api_exports() -> None:
    expected = {
        "__version__",
        "AttributeFlattenFilter",
        "ContextTokens",
        "FunctionLogger",
        "JsonFormatter",
        "RedactionFilter",
        "SamplingFilter",
        "get_logging_metadata",
        "get_logger",
        "inject_context",
        "install_context_factory",
        "logging_context",
        "reset_context",
        "restore_context",
        "uninstall_context_factory",
        "setup_logging",
        "with_context",
    }
    assert set(afl.__all__) == expected
    assert callable(afl.get_logger)
    assert callable(afl.inject_context)
    assert callable(afl.setup_logging)
    assert JsonFormatter is afl.JsonFormatter
