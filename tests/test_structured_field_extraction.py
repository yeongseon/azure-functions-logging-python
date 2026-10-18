"""Local (non-Azure) regression tests for the structured-field extraction
used by tests/e2e/test_logging_e2e.py::test_structured_log_appears_in_app_insights
(#590).

These exercise _extract_structured_fields() directly with synthetic App
Insights row fixtures -- no HTTP, Azure CLI, or cloud request. Intentionally
outside tests/e2e/: that package's module-level `pytestmark = pytest.mark.e2e`
would otherwise exclude these from the default unit suite, but this function
is pure and needs no E2E_BASE_URL at all. Loaded via importlib (not a normal
package import) to avoid mypy's dual module-path resolution conflict between
"e2e.test_logging_e2e" and "tests.e2e.test_logging_e2e".
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_e2e_logging_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_e2e_logging_under_test", _REPO_ROOT / "tests" / "e2e" / "test_logging_e2e.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_extract_structured_fields = _load_e2e_logging_module()._extract_structured_fields

_CORRELATION_ID = "local-ci-control"


class TestJsonMessageShape:
    def test_extracts_all_fields_from_structured_json_message(self) -> None:
        row = {
            "message": (
                '{"invocation_id": "inv-123", "function_name": "logme", '
                '"cold_start": true, "extra": {"correlation_id": "local-ci-control", '
                '"endpoint": "logme"}}'
            )
        }

        fields = _extract_structured_fields(row)

        assert fields == {
            "invocation_id": "inv-123",
            "function_name": "logme",
            "cold_start": True,
            "correlation_id": "local-ci-control",
        }


class TestCustomDimensionsShape:
    def test_extracts_all_fields_from_promoted_custom_dimensions(self) -> None:
        row = {
            "message": "Processing request correlation_id=local-ci-control",
            "customDimensions": (
                '{"invocation_id": "inv-456", "function_name": "logme", '
                '"cold_start": false, "correlation_id": "local-ci-control"}'
            ),
        }

        fields = _extract_structured_fields(row)

        assert fields == {
            "invocation_id": "inv-456",
            "function_name": "logme",
            "cold_start": False,
            "correlation_id": "local-ci-control",
        }

    def test_extracts_fields_from_already_parsed_custom_dimensions_dict(self) -> None:
        """Some az CLI output shapes may already deserialize customDimensions
        into a dict rather than leaving it as a JSON string."""
        row = {
            "message": "plain",
            "customDimensions": {
                "invocation_id": "inv-789",
                "function_name": "logme",
                "cold_start": True,
                "correlation_id": "local-ci-control",
            },
        }

        fields = _extract_structured_fields(row)

        assert fields is not None
        assert fields["invocation_id"] == "inv-789"


class TestNegativeFixtures:
    def test_plain_message_with_no_structured_payload_returns_none(self) -> None:
        """Regression (#590): the exact scenario the issue's own probe
        demonstrated -- a plain message containing the correlation string
        in free text, with no JSON structure and no customDimensions, must
        not be mistaken for a structured record."""
        row = {"message": f"Processing request correlation_id={_CORRELATION_ID}"}

        assert _extract_structured_fields(row) is None

    def test_json_message_missing_invocation_id_falls_through(self) -> None:
        """A JSON message that happens to parse but lacks the expected
        invocation_id key must not be treated as a valid structured
        payload -- and must still check customDimensions as a fallback."""
        row = {"message": '{"some_other_field": "value"}'}

        assert _extract_structured_fields(row) is None

    def test_malformed_custom_dimensions_json_does_not_raise(self) -> None:
        row = {"message": "plain", "customDimensions": "{not valid json"}

        assert _extract_structured_fields(row) is None

    def test_mismatched_correlation_id_is_still_extracted_for_caller_to_reject(self) -> None:
        """The extraction function itself does not filter by correlation_id
        -- that comparison is the caller's job (matching the row against
        the specific request under test). A row for a DIFFERENT invocation
        must still yield its own (non-matching) correlation_id, not None,
        so the caller can correctly decide it does not match."""
        row = {
            "message": (
                '{"invocation_id": "inv-other", "function_name": "logme", '
                '"cold_start": true, "extra": {"correlation_id": "some-other-request"}}'
            )
        }

        fields = _extract_structured_fields(row)

        assert fields is not None
        assert fields["correlation_id"] == "some-other-request"
        assert fields["correlation_id"] != _CORRELATION_ID

    def test_non_dict_extra_does_not_raise(self) -> None:
        row = {
            "message": (
                '{"invocation_id": "inv-1", "function_name": "logme", '
                '"cold_start": true, "extra": "not-a-dict"}'
            )
        }

        fields = _extract_structured_fields(row)

        assert fields is not None
        assert fields["correlation_id"] is None
