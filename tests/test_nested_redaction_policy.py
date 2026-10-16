from __future__ import annotations

import io
import json
import logging

from azure_functions_logging import JsonFormatter, RedactionFilter

_CUSTOM_SECRET = "CUSTOMREVIEW123456"


def test_custom_pattern_masks_supported_nested_container_leaves() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter(patterns=[_CUSTOM_SECRET]))
    logger = logging.Logger("nested-redaction", logging.INFO)
    logger.addHandler(handler)

    logger.info(
        "payload",
        extra={
            "plain": _CUSTOM_SECRET,
            "payload": {"note": _CUSTOM_SECRET, "password": _CUSTOM_SECRET},
            "items": ({"password": _CUSTOM_SECRET},),
        },
    )

    output = stream.getvalue()
    payload = json.loads(output)["extra"]
    assert payload == {
        "plain": "***",
        "payload": {"note": "***", "password": "***"},
        "items": [{"password": "***"}],
    }
    assert _CUSTOM_SECRET not in output


def test_custom_pattern_masks_exception_text() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter(patterns=[_CUSTOM_SECRET]))
    logger = logging.Logger("nested-redaction-exception", logging.INFO)
    logger.addHandler(handler)

    try:
        raise ValueError(f"opaque failure {_CUSTOM_SECRET}")
    except ValueError:
        logger.exception("failed")

    assert "ValueError: opaque failure ***" in json.loads(stream.getvalue())["exception"]
    assert _CUSTOM_SECRET not in stream.getvalue()
