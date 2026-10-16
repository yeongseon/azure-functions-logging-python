from __future__ import annotations

import io
import json
import logging

from azure_functions_logging import JsonFormatter, RedactionFilter

_CUSTOM_VALUE = "CUSTOMREVIEW123456"


def test_custom_pattern_masks_supported_nested_container_leaves() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter(patterns=[_CUSTOM_VALUE]))
    logger = logging.Logger("nested-redaction", logging.INFO)
    logger.addHandler(handler)

    logger.info(
        "payload",
        extra={
            "plain": _CUSTOM_VALUE,
            "payload": {"note": _CUSTOM_VALUE, "password": _CUSTOM_VALUE},
            "items": ({"password": _CUSTOM_VALUE},),
        },
    )

    output = stream.getvalue()
    payload = json.loads(output)["extra"]
    assert payload == {
        "plain": "***",
        "payload": {"note": "***", "password": "***"},
        "items": [{"password": "***"}],
    }
    assert _CUSTOM_VALUE not in output


def test_custom_pattern_masks_exception_text() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter(patterns=[_CUSTOM_VALUE]))
    logger = logging.Logger("nested-redaction-exception", logging.INFO)
    logger.addHandler(handler)

    try:
        raise ValueError(f"opaque failure {_CUSTOM_VALUE}")
    except ValueError:
        logger.exception("failed")

    assert "ValueError: opaque failure ***" in json.loads(stream.getvalue())["exception"]
    assert _CUSTOM_VALUE not in stream.getvalue()
