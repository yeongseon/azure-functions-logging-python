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


def test_extra_context_var_unbound_does_not_break_filter_mode_logging() -> None:
    """Regression (#583): a valid ContextVar without a default must not make
    ordinary logging raise -- exercised through the full public pipeline
    (setup_logging + ContextFilter) with both FunctionLogger and a plain
    stdlib logger, in the default (filter) mode."""
    import contextvars

    logger_name = "afl.integration.unbound.filter"
    target = logging.getLogger(logger_name)
    target.handlers.clear()
    target.filters.clear()

    tenant_var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_integration_filter")
    with patch.dict(os.environ, {}, clear=True):
        setup_logging(logger_name=logger_name, extra_context_vars={"tenant": tenant_var})

    stream = io.StringIO()
    handler = target.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)

    get_logger(logger_name).info("via FunctionLogger")
    logging.getLogger(logger_name).info("via stdlib logger")

    output = stream.getvalue()
    assert "via FunctionLogger" in output
    assert "via stdlib logger" in output

    target.handlers.clear()
    target.filters.clear()


def test_extra_context_var_unbound_does_not_break_factory_mode_logging() -> None:
    """Regression (#583): the same guarantee in use_record_factory=True mode,
    where an unhandled LookupError would also break every other logger in
    the process (the factory is process-wide, not per-logger)."""
    import contextvars

    logger_name = "afl.integration.unbound.factory"
    target = logging.getLogger(logger_name)
    target.handlers.clear()
    target.filters.clear()
    old_factory = logging.getLogRecordFactory()

    tenant_var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_integration_factory")
    try:
        with patch.dict(os.environ, {}, clear=True):
            setup_logging(
                logger_name=logger_name,
                use_record_factory=True,
                extra_context_vars={"tenant": tenant_var},
            )

        stream = io.StringIO()
        handler = target.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        handler.setStream(stream)

        get_logger(logger_name).info("via FunctionLogger")
        logging.getLogger(logger_name).info("via stdlib logger")

        output = stream.getvalue()
        assert "via FunctionLogger" in output
        assert "via stdlib logger" in output
    finally:
        logging.setLogRecordFactory(old_factory)
        target.handlers.clear()
        target.filters.clear()

    logger = get_logger("afl.integration.type")
    assert isinstance(logger, FunctionLogger)


def test_public_api_exports() -> None:
    expected = {
        "__version__",
        "AttributeFlattenFilter",
        "attach_secure_redaction",
        "configure_secure_redaction",
        "ContextTokens",
        "DEFAULT_REDACTION_PATTERNS",
        "FunctionLogger",
        "JsonFormatter",
        "RedactionFilter",
        "SamplingFilter",
        "get_logging_metadata",
        "get_logger",
        "inject_context",
        "IsolatedHandler",
        "logging_context",
        "propagate_context",
        "PropagatingExecutor",
        "propagating_executor",
        "reset_context",
        "restore_context",
        "setup_logging",
        "with_context",
    }
    assert set(afl.__all__) == expected
    assert callable(afl.get_logger)
    assert callable(afl.inject_context)
    assert callable(afl.setup_logging)
    assert JsonFormatter is afl.JsonFormatter
