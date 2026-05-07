"""Tests for the public API surface of azure-functions-logging."""

import azure_functions_logging  # pyright: ignore[reportMissingImports]


class TestAPISurface:
    """Verify __all__ matches exactly the declared public names."""

    def test_all_exports(self) -> None:
        assert set(azure_functions_logging.__all__) == {
            "__version__",
            "FunctionLogger",
            "JsonFormatter",
            "RedactionFilter",
            "SamplingFilter",
            "get_logging_metadata",
            "get_logger",
            "inject_context",
            "logging_context",
            "reset_context",
            "setup_logging",
            "with_context",
        }

    def test_version_is_0_5_0(self) -> None:
        assert azure_functions_logging.__version__ == "0.5.4"

    def test_version_is_string(self) -> None:
        assert isinstance(azure_functions_logging.__version__, str)

    def test_public_names_are_importable(self) -> None:
        from azure_functions_logging import (  # noqa: F401  # pyright: ignore[reportMissingImports]
            FunctionLogger,
            JsonFormatter,
            RedactionFilter,
            SamplingFilter,
            get_logger,
            get_logging_metadata,
            inject_context,
            logging_context,
            reset_context,
        )

    def test_get_logger_is_callable(self) -> None:
        assert callable(azure_functions_logging.get_logger)

    def test_setup_logging_is_callable(self) -> None:
        assert callable(azure_functions_logging.setup_logging)
