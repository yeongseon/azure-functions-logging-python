"""Tests for the public API surface of azure-functions-logging."""

import azure_functions_logging  # pyright: ignore[reportMissingImports]


class TestAPISurface:
    """Verify __all__ matches exactly the declared public names."""

    def test_all_exports(self) -> None:
        assert set(azure_functions_logging.__all__) == {
            "__version__",
            "AttributeFlattenFilter",
            "attach_secure_redaction",
            "configure_secure_redaction",
            "ContextTokens",
            "DEFAULT_REDACTION_PATTERNS",
            "FunctionLogger",
            "JsonFormatter",
            "IsolatedHandler",
            "RedactionFilter",
            "SamplingFilter",
            "get_logging_metadata",
            "get_logger",
            "inject_context",
            "logging_context",
            "propagate_context",
            "PropagatingExecutor",
            "propagating_executor",
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
            IsolatedHandler,
            JsonFormatter,
            PropagatingExecutor,
            RedactionFilter,
            SamplingFilter,
            get_logger,
            get_logging_metadata,
            inject_context,
            logging_context,
            propagate_context,
            propagating_executor,
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


class TestDocumentedInventory:
    """Guard: the docs/architecture.md public-API inventory equals ``__all__``."""

    _START = "<!-- public-api:start -->"
    _END = "<!-- public-api:end -->"

    def _documented(self) -> set[str]:
        from pathlib import Path
        import re

        text = (Path(__file__).resolve().parents[1] / "docs" / "architecture.md").read_text(
            encoding="utf-8"
        )
        assert self._START in text and self._END in text, "public-api markers missing"
        block = text.split(self._START, 1)[1].split(self._END, 1)[0]
        return set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", block))

    def test_architecture_inventory_matches_all(self) -> None:
        documented = self._documented()
        exported = set(azure_functions_logging.__all__)
        missing = sorted(exported - documented)
        extra = sorted(documented - exported)
        assert not missing and not extra, (
            "docs/architecture.md public-API inventory drifted from __all__: "
            f"undocumented exports={missing}, documented but not exported={extra}"
        )

    def test_assistant_indexes_name_every_public_symbol(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        for name in ("llms.txt", "llms-full.txt"):
            text = (root / name).read_text(encoding="utf-8")
            missing = sorted(
                n for n in azure_functions_logging.__all__ if n != "__version__" and n not in text
            )
            assert not missing, f"{name} does not mention public symbols: {missing}"
