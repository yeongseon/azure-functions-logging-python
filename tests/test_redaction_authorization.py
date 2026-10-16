from __future__ import annotations

import io
import json
import logging

import pytest

from azure_functions_logging import (
    DEFAULT_REDACTION_PATTERNS,
    JsonFormatter,
    RedactionFilter,
)
from azure_functions_logging._redaction import mask_patterns

_SYNTHETIC_TOKEN = "REVIEWOPAQUE123456"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"Bearer {_SYNTHETIC_TOKEN}", "Bearer ***"),
        (f"Authorization: Bearer {_SYNTHETIC_TOKEN}", "Authorization: Bearer ***"),
        (f"authorization=Bearer {_SYNTHETIC_TOKEN}", "authorization=Bearer ***"),
        (f"AUTHORIZATION : bearer   {_SYNTHETIC_TOKEN}", "AUTHORIZATION : bearer   ***"),
    ],
)
def test_mask_patterns_masks_complete_authorization_token(text: str, expected: str) -> None:
    masked = mask_patterns(text, DEFAULT_REDACTION_PATTERNS)

    assert masked == expected
    assert _SYNTHETIC_TOKEN not in masked


def test_mask_patterns_masks_multiple_authorization_tokens() -> None:
    text = f"Authorization: Bearer {_SYNTHETIC_TOKEN}; authorization=Bearer {_SYNTHETIC_TOKEN}"

    masked = mask_patterns(text, DEFAULT_REDACTION_PATTERNS)

    assert masked.count("Bearer ***") == 2
    assert _SYNTHETIC_TOKEN not in masked


@pytest.mark.parametrize("formatter", [logging.Formatter("%(message)s"), JsonFormatter()])
def test_redaction_filter_masks_parameterized_authorization_handler_output(
    formatter: logging.Formatter,
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.addFilter(RedactionFilter(patterns=DEFAULT_REDACTION_PATTERNS))
    logger = logging.Logger("authorization-redaction", logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    logger.info("header %s", f"Authorization: Bearer {_SYNTHETIC_TOKEN}")

    output = stream.getvalue()
    if isinstance(formatter, JsonFormatter):
        assert json.loads(output)["message"] == "header Authorization: Bearer ***"
    else:
        assert output.strip() == "header Authorization: Bearer ***"
    assert _SYNTHETIC_TOKEN not in output
