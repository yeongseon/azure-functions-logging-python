"""Tests for the typed cross-package metadata contract (``_metadata``)."""

from __future__ import annotations

from azure_functions_logging._metadata import (
    LOGGING_METADATA_VERSION,
    METADATA_ATTR,
    NAMESPACE,
    read_logging_metadata,
    set_logging_metadata,
)


class TestContractConstants:
    def test_attr_name_is_toolkit_convention(self) -> None:
        assert METADATA_ATTR == "_azure_functions_metadata"

    def test_namespace_is_logging(self) -> None:
        assert NAMESPACE == "logging"

    def test_version_constant(self) -> None:
        assert LOGGING_METADATA_VERSION == 1


class TestSetLoggingMetadata:
    def test_writes_payload_onto_wrapper_only(self) -> None:
        def func() -> None:
            pass

        def wrapper() -> None:
            pass

        set_logging_metadata(wrapper, func, {"version": 1, "context_param": "context"})

        assert not hasattr(func, METADATA_ATTR)
        meta = getattr(wrapper, METADATA_ATTR)
        assert meta == {"logging": {"version": 1, "context_param": "context"}}

    def test_seeds_from_existing_namespaces_on_func(self) -> None:
        def func() -> None:
            pass

        def wrapper() -> None:
            pass

        setattr(func, METADATA_ATTR, {"db": {"version": 1, "bindings": []}})
        set_logging_metadata(wrapper, func, {"version": 1, "context_param": "ctx"})

        meta = getattr(wrapper, METADATA_ATTR)
        assert meta["db"] == {"version": 1, "bindings": []}
        assert meta["logging"] == {"version": 1, "context_param": "ctx"}

    def test_ignores_non_dict_existing_attr(self) -> None:
        def func() -> None:
            pass

        def wrapper() -> None:
            pass

        setattr(func, METADATA_ATTR, "not-a-dict")
        set_logging_metadata(wrapper, func, {"version": 1, "context_param": "context"})

        meta = getattr(wrapper, METADATA_ATTR)
        assert meta == {"logging": {"version": 1, "context_param": "context"}}


class TestReadLoggingMetadata:
    def test_returns_payload_when_present(self) -> None:
        def func() -> None:
            pass

        setattr(func, METADATA_ATTR, {"logging": {"version": 1, "context_param": "c"}})
        assert read_logging_metadata(func) == {"version": 1, "context_param": "c"}

    def test_returns_none_when_attr_missing(self) -> None:
        def func() -> None:
            pass

        assert read_logging_metadata(func) is None

    def test_returns_none_when_attr_not_dict(self) -> None:
        def func() -> None:
            pass

        setattr(func, METADATA_ATTR, "not-a-dict")
        assert read_logging_metadata(func) is None

    def test_returns_none_when_namespace_absent(self) -> None:
        def func() -> None:
            pass

        setattr(func, METADATA_ATTR, {"db": {"version": 1}})
        assert read_logging_metadata(func) is None

    def test_returns_none_when_namespace_not_dict(self) -> None:
        def func() -> None:
            pass

        setattr(func, METADATA_ATTR, {"logging": "not-a-dict"})
        assert read_logging_metadata(func) is None
