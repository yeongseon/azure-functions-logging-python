from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock

import pytest

from azure_functions_logging._logger import FunctionLogger


def _mock_underlying_logger() -> MagicMock:
    logger = MagicMock(spec=logging.Logger)
    logger.name = "mock.logger"
    logger.isEnabledFor.return_value = True
    logger.getEffectiveLevel.return_value = logging.INFO
    return logger


def test_function_logger_delegates_to_underlying_logger() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.info("hello")

    underlying.log.assert_called_once()
    args, kwargs = underlying.log.call_args
    assert args[0] == logging.INFO
    assert args[1] == "hello"
    assert kwargs["extra"] == {}


def test_bind_returns_new_instance_with_merged_context() -> None:
    logger = FunctionLogger(_mock_underlying_logger())
    bound = logger.bind(a=1, b=2)

    assert bound is not logger
    assert bound._context == {"a": 1, "b": 2}


def test_bind_does_not_mutate_original() -> None:
    logger = FunctionLogger(_mock_underlying_logger())
    _ = logger.bind(a=1)

    assert logger._context == {}


def test_bind_chaining_merges_context() -> None:
    logger = FunctionLogger(_mock_underlying_logger())
    chained = logger.bind(a=1).bind(b=2)

    assert chained._context == {"a": 1, "b": 2}


def test_clear_context() -> None:
    logger = FunctionLogger(_mock_underlying_logger()).bind(a=1)

    logger.clear_context()

    assert logger._context == {}


def test_all_log_methods() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    logger.error("e")
    logger.critical("c")
    logger.exception("x")

    assert underlying.log.call_count == 6
    levels = [call.args[0] for call in underlying.log.call_args_list]
    assert levels == [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
        logging.ERROR,
    ]
    assert underlying.log.call_args_list[-1].kwargs["exc_info"] is True


def test_extra_from_bind_passed_to_underlying_logger() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying).bind(user_id="u1")

    logger.info("msg", extra={"request_id": "r1"})

    _, kwargs = underlying.log.call_args
    assert kwargs["extra"] == {"request_id": "r1", "user_id": "u1"}


def test_arbitrary_kwargs_are_merged_into_extra() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying).bind(function_id="f1")

    logger.info("order accepted", order_id="o-999", tenant_id="t-1")

    _, kwargs = underlying.log.call_args
    assert kwargs["extra"] == {
        "order_id": "o-999",
        "tenant_id": "t-1",
        "function_id": "f1",
    }


def test_is_enabled_for_get_effective_level_and_set_level() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.setLevel(logging.DEBUG)
    underlying.setLevel.assert_called_once_with(logging.DEBUG)

    assert logger.isEnabledFor(logging.INFO) is True
    underlying.isEnabledFor.assert_called_with(logging.INFO)

    assert logger.getEffectiveLevel() == logging.INFO
    underlying.getEffectiveLevel.assert_called_once_with()


def test_name_property() -> None:
    logger = FunctionLogger(_mock_underlying_logger())
    assert logger.name == "mock.logger"


def test_log_returns_early_when_level_disabled() -> None:
    underlying = _mock_underlying_logger()
    underlying.isEnabledFor.return_value = False
    logger = FunctionLogger(underlying)

    logger.info("should not log", order_id="o-999")

    underlying.log.assert_not_called()


def test_reserved_logrecord_keys_in_kwargs_are_prefixed_not_raised() -> None:
    """Issue #77: kwargs colliding with LogRecord reserved attrs must not crash."""
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.info("hi", name="custom", message="user-supplied", levelname="INFO")

    underlying.log.assert_called_once()
    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    assert extra["extra_name"] == "custom"
    assert extra["extra_message"] == "user-supplied"
    assert extra["extra_levelname"] == "INFO"
    assert "name" not in extra
    assert "message" not in extra
    assert "levelname" not in extra


def test_reserved_keys_in_explicit_extra_arg_are_also_prefixed() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.info("hi", extra={"name": "custom", "user_id": "u-1"})

    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    assert extra["extra_name"] == "custom"
    assert extra["user_id"] == "u-1"


def test_non_reserved_kwargs_still_pass_through_unchanged() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.info("hi", order_id="o-1", region="eastus")

    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    assert extra == {"order_id": "o-1", "region": "eastus"}


def test_reserved_keys_via_real_stdlib_logger_does_not_raise() -> None:
    """End-to-end: the previously crashing call must now succeed against real stdlib."""
    import logging as stdlib_logging

    real_logger = stdlib_logging.getLogger("test.reserved.keys.regression")
    real_logger.addHandler(stdlib_logging.NullHandler())
    real_logger.setLevel(stdlib_logging.INFO)
    logger = FunctionLogger(real_logger)

    logger.info("hi", name="custom", message="user-supplied")


def test_reserved_keys_are_derived_from_makelogrecord() -> None:
    """Issue #83: the reserved set is derived from the running interpreter's LogRecord."""
    import logging as stdlib_logging

    from azure_functions_logging._logger import _RESERVED_LOG_RECORD_KEYS

    derived = set(stdlib_logging.makeLogRecord({}).__dict__)
    # Every attribute the stdlib puts on a fresh LogRecord must be reserved.
    assert derived <= _RESERVED_LOG_RECORD_KEYS
    # Computed-by-formatter keys are explicitly added even though they are not in __dict__.
    assert {"message", "asctime"} <= _RESERVED_LOG_RECORD_KEYS
    # Library-injected context keys remain reserved.
    assert {"invocation_id", "function_name", "trace_id", "cold_start"} <= _RESERVED_LOG_RECORD_KEYS


@pytest.mark.skipif(sys.version_info < (3, 12), reason="taskName was added in 3.12")
def test_taskname_is_reserved_on_python_3_12_plus() -> None:
    """Issue #83: taskName (Python 3.12+) must be picked up via makeLogRecord-based derivation."""
    from azure_functions_logging._logger import _RESERVED_LOG_RECORD_KEYS

    assert "taskName" in _RESERVED_LOG_RECORD_KEYS


def test_taskname_is_reserved_on_all_supported_versions_for_backward_compat() -> None:
    """Issue #83: explicit forward-compat set keeps taskName reserved on 3.10/3.11 too."""
    from azure_functions_logging._logger import _RESERVED_LOG_RECORD_KEYS

    assert "taskName" in _RESERVED_LOG_RECORD_KEYS
def test_merge_precedence_kwargs_override_extra_override_bind() -> None:
    """Issue #95: per-call kwargs > explicit extra > bind context."""
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying).bind(key="from_bind", only_bind="b")

    logger.info("msg", extra={"key": "from_extra", "only_extra": "e"}, key="from_kwarg")

    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    # kwargs wins over extra wins over bind
    assert extra["key"] == "from_kwarg"
    assert extra["only_extra"] == "e"
    assert extra["only_bind"] == "b"


def test_merge_precedence_extra_overrides_bind() -> None:
    """Issue #95: explicit extra= overrides bind context."""
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying).bind(env="staging")

    logger.info("msg", extra={"env": "production"})

    _, kwargs = underlying.log.call_args
    assert kwargs["extra"]["env"] == "production"


def test_merge_precedence_kwargs_override_bind() -> None:
    """Issue #95: per-call kwargs override bind context."""
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying).bind(request_id="old")

    logger.info("msg", request_id="new")

    _, kwargs = underlying.log.call_args
    assert kwargs["extra"]["request_id"] == "new"


def test_exc_info_and_stack_info_do_not_leak_into_extra() -> None:
    """Regression: control kwargs (exc_info, stack_info, stacklevel) must not appear in extra."""
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying).bind(ctx="val")

    logger.exception("boom", order_id="o-1")

    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    assert "exc_info" not in extra
    assert "stack_info" not in extra
    assert "stacklevel" not in extra
    assert extra == {"ctx": "val", "order_id": "o-1"}


def test_sanitize_extra_double_prefix_conflict() -> None:
    """Edge case: if both 'name' and 'extra_name' are supplied, both are preserved."""
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.info("hi", name="collides", extra_name="user-supplied")

    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    # 'name' is reserved -> renamed to 'extra_name' first
    # then 'extra_name' (non-reserved) collides with existing -> becomes 'extra_name_2'
    assert extra["extra_name"] == "collides"
    assert extra["extra_name_2"] == "user-supplied"
    assert "name" not in extra



# ---------------------------------------------------------------------------
# log() and hasHandlers() stdlib parity (issue #103)
# ---------------------------------------------------------------------------


def test_log_dispatches_at_arbitrary_level() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL):
        underlying.log.reset_mock()
        logger.log(level, "msg-%s" % level)
        underlying.log.assert_called_once()
        args, _ = underlying.log.call_args
        assert args[0] == level


def test_log_honors_bind_extra_kwargs_precedence() -> None:
    """bind < extra < kwargs ordering must match level-specific methods."""
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying).bind(field="from-bind", common="bind-only")

    logger.log(
        logging.WARNING,
        "hi",
        field="from-kwargs",
        extra={"field": "from-extra", "only_extra": True},
    )

    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    assert extra["field"] == "from-kwargs"
    assert extra["only_extra"] is True
    assert extra["common"] == "bind-only"


def test_log_sanitizes_reserved_keys() -> None:
    underlying = _mock_underlying_logger()
    logger = FunctionLogger(underlying)

    logger.log(logging.INFO, "hi", name="shadow")

    _, kwargs = underlying.log.call_args
    extra = kwargs["extra"]
    assert "name" not in extra
    assert extra["extra_name"] == "shadow"


def test_log_skipped_when_level_disabled() -> None:
    underlying = _mock_underlying_logger()
    underlying.isEnabledFor.return_value = False
    logger = FunctionLogger(underlying)

    logger.log(logging.DEBUG, "nope")

    underlying.log.assert_not_called()


def test_has_handlers_true() -> None:
    underlying = _mock_underlying_logger()
    underlying.hasHandlers.return_value = True
    logger = FunctionLogger(underlying)
    assert logger.hasHandlers() is True
    underlying.hasHandlers.assert_called_once_with()


def test_has_handlers_false() -> None:
    underlying = _mock_underlying_logger()
    underlying.hasHandlers.return_value = False
    logger = FunctionLogger(underlying)
    assert logger.hasHandlers() is False


def test_stdlib_record_keys_are_immune_to_custom_logrecord_factory() -> None:
    """_STDLIB_RECORD_KEYS must equal the base LogRecord fields regardless of any
    LogRecordFactory currently installed.  It is derived from logging.LogRecord(...)
    directly, not from logging.makeLogRecord({}) which respects the ambient factory.
    A third-party factory installed before our module loads must not cause its
    injected fields to be misclassified as reserved stdlib attributes."""
    from azure_functions_logging._logger import _FORWARD_COMPAT_RECORD_KEYS, _STDLIB_RECORD_KEYS

    original_factory = logging.getLogRecordFactory()

    def polluting_factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = original_factory(*args, **kwargs)
        record._third_party_injected_field = "injected"
        return record

    logging.setLogRecordFactory(polluting_factory)
    try:
        # Confirm the factory is polluting makeLogRecord
        factory_fields = set(logging.makeLogRecord({}).__dict__)
        assert "_third_party_injected_field" in factory_fields, \
            "Precondition failed: factory should inject field into makeLogRecord output"

        # _STDLIB_RECORD_KEYS must match what the base class produces, not the factory
        expected = (
            frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
            | _FORWARD_COMPAT_RECORD_KEYS
        )
        assert _STDLIB_RECORD_KEYS == expected
        assert "_third_party_injected_field" not in _STDLIB_RECORD_KEYS, \
            "Factory-injected fields must not appear in _STDLIB_RECORD_KEYS"
    finally:
        logging.setLogRecordFactory(original_factory)