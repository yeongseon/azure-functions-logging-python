"""Tests for the public API surface of azure-functions-logging."""

import azure_functions_logging  # pyright: ignore[reportMissingImports]


class TestAPISurface:
    """Verify __all__ matches exactly the declared public names."""

    def test_all_exports(self) -> None:
        assert set(azure_functions_logging.__all__) == {
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
            "logging_context",
            "propagate_context",
            "reset_context",
            "restore_context",
            "setup_logging",
            "with_context",
        }

    def test_version_matches_distribution_metadata(self) -> None:
        from importlib.metadata import version

        assert azure_functions_logging.__version__ == version("azure-functions-logging")

    def test_version_is_string(self) -> None:
        assert isinstance(azure_functions_logging.__version__, str)

    def test_public_names_are_importable(self) -> None:
        from azure_functions_logging import (  # noqa: F401  # pyright: ignore[reportMissingImports]
            AttributeFlattenFilter,
            ContextTokens,
            FunctionLogger,
            JsonFormatter,
            RedactionFilter,
            SamplingFilter,
            get_logger,
            get_logging_metadata,
            inject_context,
            logging_context,
            propagate_context,
            reset_context,
            restore_context,
        )

    def test_get_logger_is_callable(self) -> None:
        assert callable(azure_functions_logging.get_logger)

    def test_setup_logging_is_callable(self) -> None:
        assert callable(azure_functions_logging.setup_logging)


class TestDocsCoverage:
    """Guard: every public symbol in ``__all__`` is documented in docs/api.md."""

    def test_every_public_symbol_documented(self) -> None:
        from pathlib import Path

        api_doc = Path(__file__).resolve().parents[1] / "docs" / "api.md"
        assert api_doc.exists(), f"API documentation file is missing: {api_doc}"
        text = api_doc.read_text(encoding="utf-8")
        missing = [
            name
            for name in azure_functions_logging.__all__
            if name != "__version__" and f"::: azure_functions_logging.{name}" not in text
        ]
        assert not missing, (
            "Public symbols missing an mkdocstrings directive "
            f"(`::: azure_functions_logging.<name>`) in docs/api.md: {missing}"
        )
