"""Runtime contract tests for azure-functions-logging.

These tests lock the observable behavior that users depend on across
environments.  They assert *outcomes* (output shape, field presence,
handler counts) rather than implementation details.

Covers:
- JSON schema contract (exact top-level keys, types, nullability)
- Context-absent contract (all context fields null without inject_context)
- Environment mode switching (standalone / Core Tools / Azure hosted)
- Duplicate output prevention (Azure mode adds zero handlers)
- Idempotency (multiple setup_logging calls produce no extra output)

Ref: https://github.com/yeongseon/azure-functions-logging/issues/23
"""

from __future__ import annotations

import io
import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from azure_functions_logging import (
    JsonFormatter,
    get_logger,
    inject_context,
    setup_logging,
)
import azure_functions_logging._context as ctx_mod
from azure_functions_logging._context import (
    ContextFilter,
    cold_start_var,
    function_name_var,
    invocation_id_var,
    trace_id_var,
)
from azure_functions_logging._formatter import ColorFormatter
import azure_functions_logging._setup as setup_mod


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Reset global state between tests."""
    setup_mod._configured_loggers.clear()
    ctx_mod._cold_start = True
    invocation_id_var.set(None)
    function_name_var.set(None)
    trace_id_var.set(None)
    cold_start_var.set(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_CONTEXT = SimpleNamespace(
    invocation_id="inv-contract",
    function_name="fn-contract",
    trace_context=SimpleNamespace(
        trace_parent="00-aaaabbbbccccddddeeeeffffaaaabbbb-1111222233334444-01"
    ),
)

# The full set of top-level keys that JsonFormatter must emit.
_JSON_SCHEMA_KEYS: set[str] = {
    "timestamp",
    "level",
    "logger",
    "message",
    "invocation_id",
    "function_name",
    "trace_id",
    "span_id",
    "cold_start",
    "exception",
    "extra",
}


def _capture_json_line(logger_name: str) -> str:
    """Set up a logger with JsonFormatter + ContextFilter and capture one line."""
    target = logging.getLogger(logger_name)
    target.handlers.clear()
    target.filters.clear()
    target.setLevel(logging.DEBUG)
    target.propagate = False

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    target.addHandler(handler)

    fl = get_logger(logger_name)
    fl.info("contract-test-message")

    target.handlers.clear()
    target.filters.clear()
    return stream.getvalue().strip()


# ---------------------------------------------------------------------------
# 1. JSON schema contract
# ---------------------------------------------------------------------------


class TestJsonSchemaContract:
    """The set of top-level keys emitted by JsonFormatter is the library's
    de-facto public contract.  Any key removal or rename is a breaking change.
    """

    def test_top_level_keys_are_exactly_the_documented_set(self) -> None:
        line = _capture_json_line("afl.contract.schema.keys")
        payload = json.loads(line)
        assert set(payload.keys()) == _JSON_SCHEMA_KEYS

    def test_output_is_valid_ndjson_single_line(self) -> None:
        line = _capture_json_line("afl.contract.schema.ndjson")
        assert "\n" not in line
        json.loads(line)  # must not raise

    def test_timestamp_is_iso8601_utc(self) -> None:
        line = _capture_json_line("afl.contract.schema.ts")
        ts = json.loads(line)["timestamp"]
        assert ts.endswith("+00:00") or ts.endswith("Z")

    def test_extra_is_always_a_dict(self) -> None:
        line = _capture_json_line("afl.contract.schema.extra")
        assert isinstance(json.loads(line)["extra"], dict)

    def test_exception_is_null_when_no_exception(self) -> None:
        line = _capture_json_line("afl.contract.schema.exc")
        assert json.loads(line)["exception"] is None


# ---------------------------------------------------------------------------
# 2. Context-absent contract
# ---------------------------------------------------------------------------


class TestContextAbsentContract:
    """When inject_context() is NOT called, all context fields must be
    explicitly null (present with value null), not missing.
    """

    def test_all_context_fields_are_null_without_inject_context(self) -> None:
        line = _capture_json_line("afl.contract.nocontext")
        payload = json.loads(line)

        assert payload["invocation_id"] is None
        assert payload["function_name"] is None
        assert payload["trace_id"] is None
        assert payload["cold_start"] is None

    def test_context_fields_are_populated_after_inject_context(self) -> None:
        inject_context(_MOCK_CONTEXT)
        line = _capture_json_line("afl.contract.withcontext")
        payload = json.loads(line)

        assert payload["invocation_id"] == "inv-contract"
        assert payload["function_name"] == "fn-contract"
        assert payload["trace_id"] == "aaaabbbbccccddddeeeeffffaaaabbbb"
        assert payload["cold_start"] is True


# ---------------------------------------------------------------------------
# 3. Environment mode switching contract
# ---------------------------------------------------------------------------

# Environment matrix:
#   Standalone (no env vars)   -> adds StreamHandler, sets level
#   Core Tools (FUNCTIONS_WORKER_RUNTIME) -> filter only, no handlers
#   Azure hosted (both vars)   -> filter only, no handlers


class TestEnvironmentModeContract:
    """setup_logging() must behave differently based on environment."""

    def test_standalone_adds_handler_with_color_formatter(self) -> None:
        name = "afl.contract.env.standalone.color"
        target = logging.getLogger(name)
        target.handlers.clear()
        target.filters.clear()

        with patch.dict(os.environ, {}, clear=True):
            setup_logging(logger_name=name, format="color")

        assert len(target.handlers) == 1
        assert isinstance(target.handlers[0].formatter, ColorFormatter)
        assert any(isinstance(f, ContextFilter) for f in target.handlers[0].filters)

        target.handlers.clear()
        target.filters.clear()

    def test_standalone_adds_handler_with_json_formatter(self) -> None:
        name = "afl.contract.env.standalone.json"
        target = logging.getLogger(name)
        target.handlers.clear()
        target.filters.clear()

        with patch.dict(os.environ, {}, clear=True):
            setup_logging(logger_name=name, format="json")

        assert len(target.handlers) == 1
        assert isinstance(target.handlers[0].formatter, JsonFormatter)

        target.handlers.clear()
        target.filters.clear()

    def test_core_tools_adds_no_handlers(self) -> None:
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        root.filters.clear()

        with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
            setup_logging()

        # No new handlers added
        assert root.handlers == original_handlers
        # ContextFilter installed on root
        assert any(isinstance(f, ContextFilter) for f in root.filters)

        root.filters.clear()

    def test_azure_hosted_adds_no_handlers(self) -> None:
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        root.filters.clear()

        env = {
            "FUNCTIONS_WORKER_RUNTIME": "python",
            "WEBSITE_INSTANCE_ID": "abc123",
        }
        with patch.dict(os.environ, env, clear=True):
            setup_logging()

        assert root.handlers == original_handlers
        assert any(isinstance(f, ContextFilter) for f in root.filters)

        root.filters.clear()


# ---------------------------------------------------------------------------
# 4. Duplicate output prevention
# ---------------------------------------------------------------------------


class TestDuplicateOutputPrevention:
    """In Azure/Core Tools environments, setup_logging must not add handlers.
    Multiple calls must not produce duplicate log lines.
    """

    def test_azure_env_produces_no_extra_handler_output(self) -> None:
        """Logging in Azure mode should use existing handlers only,
        not add new ones that would cause duplicate output.
        """
        root = logging.getLogger()
        root.filters.clear()

        stream = io.StringIO()
        existing_handler = logging.StreamHandler(stream)
        existing_handler.setFormatter(logging.Formatter("%(message)s"))
        root.handlers = [existing_handler]

        with patch.dict(os.environ, {"FUNCTIONS_WORKER_RUNTIME": "python"}, clear=True):
            setup_logging()

        # Only the one pre-existing handler should remain
        assert len(root.handlers) == 1
        assert root.handlers[0] is existing_handler

        root.handlers = []
        root.filters.clear()

    def test_standalone_idempotent_no_duplicate_handlers(self) -> None:
        """Calling setup_logging() twice in standalone mode must not
        add a second handler.
        """
        name = "afl.contract.dup.standalone"
        target = logging.getLogger(name)
        target.handlers.clear()
        target.filters.clear()

        with patch.dict(os.environ, {}, clear=True):
            setup_logging(logger_name=name)
            handler_count_after_first = len(target.handlers)
            # Second call — idempotent
            setup_logging(logger_name=name)

        assert len(target.handlers) == handler_count_after_first

        target.handlers.clear()
        target.filters.clear()

    def test_standalone_single_log_produces_single_output_line(self) -> None:
        """One logger.info() call must produce exactly one output line."""
        name = "afl.contract.dup.output"
        target = logging.getLogger(name)
        target.handlers.clear()
        target.filters.clear()
        target.propagate = False

        stream = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            setup_logging(logger_name=name, format="json")

        handler = target.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        handler.setStream(stream)

        fl = get_logger(name)
        fl.info("single-line-test")

        lines = [ln for ln in stream.getvalue().split("\n") if ln.strip()]
        assert len(lines) == 1

        target.handlers.clear()
        target.filters.clear()
